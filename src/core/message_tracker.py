from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import re
import logging
import json

@dataclass
class MessageHistory:
    original_text: str
    edit_history: List[Dict[str, any]]
    original_sentiment_score: float
    last_check: datetime
    user_id: int
    username: str

class MessageTracker:
    def __init__(self, text_analyzer, message_broker):
        self.text_analyzer = text_analyzer
        self.message_broker = message_broker
        self.message_history: Dict[int, MessageHistory] = {}
        self.suspicious_edits: Dict[int, List[Dict]] = {}
        
        # Регулярные выражения для проверки спама
        self.spam_patterns = [
            r'\b(?:https?://)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]+\b',  # Telegram ссылки
            r'\b\+\d{10,}\b',  # Телефонные номера
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',  # Email
            r'\b(?:крипто|заработок|инвестиции|доход|прибыль).{0,30}(?:гарантированный|быстрый|легкий)\b',
            r'\b(?:казино|ставки|букмекер|прогнозы)\b',
            r'\b(?:бинанс|биткоин|эфир|крипта|токен).{0,30}(?:рост|памп|профит)\b',
            r'\b(?:работа|подработка|доход).{0,30}(?:дома|удаленно|онлайн)\b'
        ]
        
        # Подозрительные домены
        self.suspicious_domains = [
            'bit.ly', 'tinyurl.com', 'goo.gl',  # Сокращатели ссылок
            'crypto', 'wallet', 'investment',    # Подозрительные домены
            'profit', 'earning', 'casino',
            'binance', 'trading', 'forex'
        ]
        
    async def track_message(self, message_id: int, text: str, 
                          sentiment_score: float, user_id: int, 
                          username: str) -> None:
        """Начать отслеживание сообщения"""
        try:
            # Сохраняем в Redis для отказоустойчивости
            message_data = {
                'original_text': text,
                'edit_history': [],
                'original_sentiment_score': sentiment_score,
                'last_check': datetime.now().isoformat(),
                'user_id': user_id,
                'username': username
            }
            
            await self.message_broker.cache_set(
                f"message_history:{message_id}",
                message_data
            )
            
            # Сохраняем в памяти
            self.message_history[message_id] = MessageHistory(
                original_text=text,
                edit_history=[],
                original_sentiment_score=sentiment_score,
                last_check=datetime.now(),
                user_id=user_id,
                username=username
            )
            
            logging.info(f"Started tracking message {message_id} from user {username}")
        except Exception as e:
            logging.error(f"Failed to track message: {e}")

    async def check_edit(self, message_id: int, new_text: str) -> Optional[Dict[str, Any]]:
        """Проверить изменение сообщения"""
        try:
            # Пытаемся получить историю из Redis
            cached_history = await self.message_broker.cache_get(f"message_history:{message_id}")
            
            if not cached_history and message_id not in self.message_history:
                return None
                
            history = self.message_history.get(message_id) or MessageHistory(**cached_history)
            
            # Анализируем новый текст
            is_negative, new_score, analysis = await self.text_analyzer.is_negative(new_text)
            
            # Проверяем резкое изменение тональности
            sentiment_change = new_score - history.original_sentiment_score
            
            edit_info = {
                'timestamp': datetime.now().isoformat(),
                'old_text': history.original_text,
                'new_text': new_text,
                'sentiment_change': sentiment_change,
                'is_negative': is_negative,
                'analysis': analysis
            }
            
            # Проверяем различные признаки подозрительности
            is_suspicious = await self._check_suspicious_factors(
                new_text=new_text,
                sentiment_change=sentiment_change,
                is_negative=is_negative
            )
            
            if is_suspicious:
                if message_id not in self.suspicious_edits:
                    self.suspicious_edits[message_id] = []
                self.suspicious_edits[message_id].append(edit_info)
                
                # Сохраняем информацию о подозрительном изменении в Redis
                await self.message_broker.cache_set(
                    f"suspicious_edit:{message_id}:{len(self.suspicious_edits[message_id])}",
                    edit_info
                )
            
            # Обновляем историю
            history.edit_history.append(edit_info)
            history.last_check = datetime.now()
            
            # Обновляем кэш
            await self.message_broker.cache_set(
                f"message_history:{message_id}",
                {
                    'original_text': history.original_text,
                    'edit_history': history.edit_history,
                    'original_sentiment_score': history.original_sentiment_score,
                    'last_check': history.last_check.isoformat(),
                    'user_id': history.user_id,
                    'username': history.username
                }
            )
            
            return {
                'is_suspicious': is_suspicious,
                'edit_info': edit_info,
                'user_id': history.user_id,
                'username': history.username
            }
            
        except Exception as e:
            logging.error(f"Error checking message edit: {e}")
            return None

    async def _check_suspicious_factors(self, new_text: str, 
                                      sentiment_change: float,
                                      is_negative: bool) -> bool:
        """Проверка различных подозрительных факторов"""
        return any([
            is_negative,                    # Текст стал негативным
            sentiment_change < -0.5,        # Резкое изменение тональности
            await self._check_spam_patterns(new_text),  # Спам-паттерны
            await self._has_suspicious_links(new_text)  # Подозрительные ссылки
        ])

    async def _check_spam_patterns(self, text: str) -> bool:
        """Проверка на спам-паттерны"""
        try:
            text_lower = text.lower()
            return any(re.search(pattern, text_lower) for pattern in self.spam_patterns)
        except Exception as e:
            logging.error(f"Error checking spam patterns: {e}")
            return False

    async def _has_suspicious_links(self, text: str) -> bool:
        """Проверка на подозрительные ссылки"""
        try:
            urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', text)
            return any(domain in url.lower() for url in urls 
                      for domain in self.suspicious_domains)
        except Exception as e:
            logging.error(f"Error checking suspicious links: {e}")
            return False

    async def cleanup_old_records(self):
        """Очистка старых записей"""
        try:
            current_time = datetime.now()
            to_remove = []
            
            for message_id, history in self.message_history.items():
                # Удаляем записи старше 7 дней
                if (current_time - history.last_check) > timedelta(days=7):
                    to_remove.append(message_id)
                    # Удаляем также из Redis
                    await self.message_broker.aioredis.delete(f"message_history:{message_id}")
                    
            for message_id in to_remove:
                del self.message_history[message_id]
                
            logging.info(f"Cleaned up {len(to_remove)} old message records")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    async def get_edit_statistics(self) -> Dict[str, int]:
        """Получение статистики по изменениям"""
        try:
            total_edits = sum(len(history.edit_history) 
                            for history in self.message_history.values())
            suspicious_edits = sum(len(edits) 
                                 for edits in self.suspicious_edits.values())
            
            return {
                'total_tracked_messages': len(self.message_history),
                'total_edits': total_edits,
                'suspicious_edits': suspicious_edits
            }
        except Exception as e:
            logging.error(f"Error getting edit statistics: {e}")
            return {
                'total_tracked_messages': 0,
                'total_edits': 0,
                'suspicious_edits': 0
            } 