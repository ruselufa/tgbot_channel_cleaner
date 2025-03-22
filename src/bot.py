import logging
from datetime import datetime, timedelta
import asyncio
import sys
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, Defaults
import traceback

from src.models import Session, User, Comment
from src.db.init_db import init_db
from src.services.user_service import UserService
from src.services.comment_service import CommentService
from src.services.message_service import MessageService
from src.services.moderator_log_service import ModeratorLogService
from src.core.text_analyzer import TextAnalyzer
from src.core.message_tracker import MessageTracker
from src.core.message_broker import MessageBroker
from config.settings import (
    BOT_TOKEN, ADMIN_CHAT_ID, MESSAGES, CHANNEL_ID,
    MAX_WARNINGS, WORKER_COUNT, DISCUSSION_GROUP_ID
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()  # Добавляем вывод в консоль
    ]
)
logger = logging.getLogger(__name__)

class HighLoadBot:
    def __init__(self):
        self.text_analyzer = TextAnalyzer()
        self.message_broker = MessageBroker()
        self.message_tracker = MessageTracker(self.text_analyzer, self.message_broker)
        self.session = Session()
        self.user_service = UserService(self.session)
        self.comment_service = CommentService(self.session)
        self.message_service = MessageService()
        print(f"\nБот запущен и настроен для работы с:\nКанал ID: {CHANNEL_ID}\nАдмин чат ID: {ADMIN_CHAT_ID}\n")
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("/stats"), KeyboardButton("/unban_user")],
            [KeyboardButton("/get_chat_id")]
        ], resize_keyboard=True)
        
        await update.message.reply_text(
            "Привет! Я бот-модератор. Я буду следить за комментариями в канале и помогать с модерацией.",
            reply_markup=keyboard
        )

    async def get_chat_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение ID чата/канала"""
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        chat_title = update.effective_chat.title if update.effective_chat.title else "Личные сообщения"
        
        await update.message.reply_text(
            f"ℹ️ Информация о чате:\n"
            f"Название: {chat_title}\n"
            f"Тип: {chat_type}\n"
            f"ID: {chat_id}\n\n"
            f"💡 Для настройки бота вам нужно:\n\n"
            f"1. Добавить бота в ваш канал как администратора\n"
            f"   и указать ID канала в файле .env:\n"
            f"   CHANNEL_ID=ваш_id_канала\n\n"
            f"2. Создать группу для администраторов,\n"
            f"   добавить туда бота и указать ID группы в файле .env:\n"
            f"   ADMIN_CHAT_ID=id_группы_админов\n\n"
            f"❗️ В группу администраторов будут приходить уведомления о:\n"
            f"• Негативных сообщениях\n"
            f"• Предупреждениях пользователей\n"
            f"• Банах пользователей\n"
            f"• Подозрительных изменениях"
        )

    async def handle_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка комментария"""
        try:
            print("\n=== Получено новое обновление ===")
            print(f"Update ID: {update.update_id}")
            print(f"Update type: {type(update).__name__}")
            print(f"Has message: {update.message is not None}")
            print(f"Has channel_post: {update.channel_post is not None}")
            print(f"Has edited_channel_post: {update.edited_channel_post is not None}")
            print(f"Raw update: {update.to_dict()}")
            print("===============================")
            
            # Определяем тип обновления и получаем сообщение
            if update.channel_post:
                message = update.channel_post
                update_type = "channel_post"
            elif update.message:
                message = update.message
                update_type = "message"
            else:
                print("Получено обновление без сообщения")
                return
                
            print(f"Тип обновления: {update_type}")
            
            # Проверяем наличие текста
            if not message.text and not (message.caption and isinstance(message.caption, str)):
                print(f"Сообщение без текста. Тип сообщения: {type(message).__name__}")
                return
                
            # Получаем текст сообщения (может быть в caption для медиа-сообщений)
            text = message.text if message.text else message.caption
            
            # Подробное логирование деталей сообщения
            message_details = (
                f"\n=== Детали сообщения ===\n"
                f"Тип обновления: {update_type}\n"
                f"Текст: {text}\n"
                f"Тип: {type(message).__name__}\n"
                f"Chat ID: {message.chat.id}\n"
                f"Message ID: {message.message_id}\n"
                f"От пользователя: {message.from_user.username if message.from_user else 'Unknown'}\n"
                f"Тип чата: {message.chat.type}\n"
                f"CHANNEL_ID из конфига: {CHANNEL_ID}\n"
                f"DISCUSSION_GROUP_ID из конфига: {DISCUSSION_GROUP_ID}\n"
                f"======================"
            )
            print(message_details)
                
            # Проверяем, что сообщение из нужного канала или группы обсуждений
            chat_id = str(message.chat.id)
            channel_id = str(CHANNEL_ID)
            discussion_id = str(DISCUSSION_GROUP_ID)
            
            # Проверяем источник сообщения
            is_from_channel = chat_id == channel_id
            is_from_discussion = chat_id == discussion_id
            
            if not (is_from_channel or is_from_discussion):
                print(f"Сообщение не из целевого канала или группы обсуждений.")
                print(f"Chat ID: {chat_id}")
                print(f"CHANNEL_ID: {channel_id}")
                print(f"DISCUSSION_GROUP_ID: {discussion_id}")
                return
                
            # Для сообщений из группы обсуждений проверяем, что это комментарий к посту из нашего канала
            if is_from_discussion and hasattr(message, 'reply_to_message'):
                reply_msg = message.reply_to_message
                if not (hasattr(reply_msg, 'forward_origin') and 
                       hasattr(reply_msg.forward_origin, 'chat') and 
                       str(reply_msg.forward_origin.chat.id) == channel_id):
                    print("Сообщение не является комментарием к посту из целевого канала")
                    return
            
            user_id = message.from_user.id if message.from_user else None
            if not user_id:
                print("Не удалось получить ID пользователя")
                return
                
            # Анализ текста
            is_negative = await self.text_analyzer.is_negative(text)
            toxicity_score = await self.text_analyzer.get_toxicity_score(text)
            emotion = await self.text_analyzer.get_emotion(text)
            
            print(f"\n=== Результаты анализа ===")
            print(f"Негативный контент: {is_negative}")
            print(f"Токсичность: {toxicity_score:.2f}")
            print(f"Эмоция: {emotion}")
            print("=========================")
            
            # Сохраняем сообщение для отслеживания изменений
            await self.message_tracker.track_message(
                message_id=message.message_id,
                text=text,
                sentiment_score=toxicity_score,
                user_id=user_id,
                username=message.from_user.username
            )
            
            # Если контент негативный
            if is_negative:
                user = await self.user_service.get_or_create_user(user_id, message.from_user.username)
                warnings_count = await self.user_service.add_warning(user_id)
                
                # Удаляем негативное сообщение
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=message.message_id
                    )
                    print(f"Удалено негативное сообщение (ID: {message.message_id})")
                except Exception as e:
                    print(f"Ошибка при удалении сообщения: {e}")
                
                # Отправляем предупреждение в группу обсуждений
                warning_text = (
                    f"⚠️ @{message.from_user.username}, ваше сообщение удалено из-за негативного контента.\n"
                    f"У вас {warnings_count} предупреждений из {MAX_WARNINGS}.\n\n"
                    f"Анализ удаленного сообщения:\n"
                    f"- Токсичность: {toxicity_score:.2f}\n"
                    f"- Эмоция: {emotion}"
                )
                
                try:
                    # Если сообщение было в группе обсуждений, отправляем предупреждение туда же
                    if is_from_discussion:
                        await context.bot.send_message(
                            chat_id=DISCUSSION_GROUP_ID,
                            text=warning_text,
                            reply_to_message_id=message.message_id if message.reply_to_message else None
                        )
                except Exception as e:
                    print(f"Ошибка при отправке предупреждения в группу: {e}")
                
                # Уведомляем администраторов
                if ADMIN_CHAT_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text=f"🚨 Негативное сообщение от @{message.from_user.username}:\n\n"
                                 f"Текст: {text}\n\n"
                                 f"Анализ:\n"
                                 f"- Негативность: {is_negative}\n"
                                 f"- Токсичность: {toxicity_score:.2f}\n"
                                 f"- Эмоция: {emotion}\n"
                                 f"- Предупреждений: {warnings_count}/{MAX_WARNINGS}\n"
                                 f"Сообщение было автоматически удалено."
                        )
                    except Exception as e:
                        print(f"Ошибка при отправке уведомления администраторам: {e}")
                    
        except Exception as e:
            print(f"Ошибка в handle_comment: {e}")
            traceback.print_exc()
        finally:
            self.session.commit()

    async def unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Разбан пользователя"""
        if not context.args:
            await update.message.reply_text(
                "Пожалуйста, укажите username пользователя для разбана.\n"
                "Пример: /unban_user @username"
            )
            return
            
        username = context.args[0].replace("@", "")
        try:
            user = self.session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"Пользователь @{username} не найден.")
                return
                
            # Сбрасываем счетчик предупреждений и снимаем бан
            user.warnings_count = 0
            user.banned_until = None
            self.session.commit()
            
            await update.message.reply_text(f"Пользователь @{username} разбанен.")
            
            # Уведомляем пользователя о разбане
            try:
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text="🎉 Вы были разбанены! Пожалуйста, соблюдайте правила общения."
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления о разбане: {e}")
                
        except Exception as e:
            logging.error(f"Ошибка при разбане пользователя: {e}")
            await update.message.reply_text("Произошла ошибка при разбане пользователя.")

    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка измененных сообщений"""
        try:
            # Получаем измененное сообщение
            message = update.edited_message or update.edited_channel_post
            if not message or not message.text:
                print("Получено обновление без текста")
                return
            
            print(f"\n=== Изменение сообщения ===")
            print(f"Chat ID: {message.chat.id}")
            print(f"Message ID: {message.message_id}")
            print(f"Новый текст: {message.text}")
            print(f"От пользователя: {message.from_user.username if message.from_user else 'Unknown'}")
            print("===========================")
            
            # Проверяем, что сообщение из нужного канала
            if str(message.chat.id) != str(CHANNEL_ID):
                print(f"Измененное сообщение не из целевого канала")
                return
            
            # Проверяем изменение
            edit_result = await self.message_tracker.check_edit(
                message_id=message.message_id,
                new_text=message.text
            )
            
            if not edit_result:
                print("Не удалось найти историю сообщения")
                return
                
            print(f"\n=== Результат проверки изменения ===")
            print(f"Подозрительное: {edit_result['is_suspicious']}")
            print(f"Изменение тональности: {edit_result['edit_info']['sentiment_change']:.2f}")
            print("===================================")
            
            if edit_result['is_suspicious']:
                # Анализируем новый текст
                is_negative = await self.text_analyzer.is_negative(message.text)
                toxicity_score = await self.text_analyzer.get_toxicity_score(message.text)
                emotion = await self.text_analyzer.get_emotion(message.text)
                
                print(f"\n=== Анализ измененного текста ===")
                print(f"Негативный контент: {is_negative}")
                print(f"Токсичность: {toxicity_score:.2f}")
                print(f"Эмоция: {emotion}")
                print("===============================")
                
                if is_negative:
                    try:
                        # Получаем пользователя
                        user_id = message.from_user.id if message.from_user else None
                        if not user_id:
                            return
                        
                        user = await self.user_service.get_or_create_user(user_id, message.from_user.username)
                        warnings_count = await self.user_service.add_warning(user_id)
                        
                        # Удаляем негативное сообщение
                        try:
                            await context.bot.delete_message(
                                chat_id=message.chat.id,
                                message_id=message.message_id
                            )
                            print(f"Удалено негативное измененное сообщение (ID: {message.message_id})")
                        except Exception as e:
                            print(f"Ошибка при удалении измененного сообщения: {e}")
                        
                        # Отправляем предупреждение
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ Предупреждение! Ваше измененное сообщение было удалено, так как содержит негативный контент.\n"
                                 f"У вас {warnings_count} предупреждений из {MAX_WARNINGS}."
                        )
                    except Exception as e:
                        print(f"Ошибка при обработке негативного изменения: {e}")
                        traceback.print_exc()
                
        except Exception as e:
            print(f"Ошибка в handle_edited_message: {e}")
            traceback.print_exc()
        finally:
            self.session.commit()

    async def handle_moderation_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка действий модерации (кнопки одобрения/отклонения)"""
        query = update.callback_query
        await query.answer()
        
        # Получаем данные из callback_data
        action, comment_id = query.data.split('_')
        comment_id = int(comment_id)
        
        try:
            # Получаем комментарий
            comment = self.session.query(Comment).filter_by(id=comment_id).first()
            if not comment:
                await query.edit_message_text("Комментарий не найден")
                return
                
            # Получаем пользователя
            user = self.session.query(User).filter_by(id=comment.user_id).first()
            
            if action == "approve":
                # Одобряем комментарий
                self.comment_service.approve_comment(comment, query.from_user.id)
                
                # Логируем действие
                log_service = ModeratorLogService(self.session)
                log_service.log_action(
                    moderator_id=query.from_user.id,
                    action='approve_comment',
                    target_user_id=user.telegram_id,
                    comment_id=comment.id
                )
                
                # Уведомляем пользователя
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=MESSAGES['comment_approved']
                )
                
                # Обновляем сообщение модератора
                await query.edit_message_text(
                    f"✅ Комментарий одобрен\n"
                    f"Пользователь: @{user.username}\n"
                    f"Текст: {comment.text}"
                )
                
            elif action == "reject":
                # Запрашиваем причину отклонения
                await query.edit_message_text(
                    f"Укажите причину отклонения комментария:\n"
                    f"Пользователь: @{user.username}\n"
                    f"Текст: {comment.text}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Оскорбление", callback_data=f"reason_insult_{comment_id}")],
                        [InlineKeyboardButton("Спам", callback_data=f"reason_spam_{comment_id}")],
                        [InlineKeyboardButton("Нецензурная лексика", callback_data=f"reason_profanity_{comment_id}")],
                        [InlineKeyboardButton("Другое", callback_data=f"reason_other_{comment_id}")]
                    ])
                )
                
            elif action.startswith("reason_"):
                # Получаем причину отклонения
                reason_type = action.split('_')[1]
                reasons = {
                    "insult": "оскорбление",
                    "spam": "спам",
                    "profanity": "нецензурная лексика",
                    "other": "нарушение правил сообщества"
                }
                reason = reasons.get(reason_type, "нарушение правил")
                
                # Отклоняем комментарий
                self.comment_service.reject_comment(comment, query.from_user.id, reason)
                
                # Добавляем предупреждение пользователю
                warnings_count, should_ban = self.user_service.add_warning(user, reason)
                
                # Логируем действие
                log_service.log_action(
                    moderator_id=query.from_user.id,
                    action='reject_comment',
                    target_user_id=user.telegram_id,
                    comment_id=comment.id,
                    details=reason
                )
                
                # Уведомляем пользователя
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=MESSAGES['comment_rejected'].format(reason)
                )
                
                if should_ban:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=MESSAGES['user_banned'].format(24)
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=MESSAGES['user_warning'].format(
                            reason, warnings_count, MAX_WARNINGS
                        )
                    )
                
                # Обновляем сообщение модератора
                await query.edit_message_text(
                    f"❌ Комментарий отклонен\n"
                    f"Пользователь: @{user.username}\n"
                    f"Причина: {reason}\n"
                    f"Предупреждений: {warnings_count}/{MAX_WARNINGS}"
                )
            
        except Exception as e:
            logger.error(f"Error handling moderation action: {e}")
            await query.edit_message_text(f"Произошла ошибка: {e}")

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            log_service = ModeratorLogService(self.session)
            
            # Получаем статистику за последние 24 часа
            stats_24h = log_service.get_moderation_stats(
                from_date=datetime.utcnow() - timedelta(days=1)
            )
            
            # Получаем общую статистику
            stats_total = log_service.get_moderation_stats()
            
            # Получаем статистику изменений
            edit_stats = await self.message_tracker.get_edit_statistics()
            
            stats_message = (
                "📊 Статистика модерации\n\n"
                "За последние 24 часа:\n"
                f"✅ Одобрено комментариев: {stats_24h['approved_comments']}\n"
                f"❌ Отклонено комментариев: {stats_24h['rejected_comments']}\n"
                f"⚠️ Выдано предупреждений: {stats_24h['warnings_issued']}\n"
                f"🚫 Заблокировано пользователей: {stats_24h['users_banned']}\n"
                f"📝 Подозрительных изменений: {stats_24h['suspicious_edits']}\n\n"
                "Общая статистика:\n"
                f"✅ Всего одобрено: {stats_total['approved_comments']}\n"
                f"❌ Всего отклонено: {stats_total['rejected_comments']}\n"
                f"⚠️ Всего предупреждений: {stats_total['warnings_issued']}\n"
                f"🚫 Всего блокировок: {stats_total['users_banned']}\n"
                f"⛔️ В черном списке: {stats_total['users_blacklisted']}\n\n"
                "Статистика изменений:\n"
                f"📝 Отслеживается сообщений: {edit_stats['total_tracked_messages']}\n"
                f"✏️ Всего изменений: {edit_stats['total_edits']}\n"
                f"⚠️ Подозрительных изменений: {edit_stats['suspicious_edits']}"
            )
            
            await update.message.reply_text(stats_message)
            
        except Exception as e:
            logger.error(f"Error showing stats: {e}")
            await update.message.reply_text("Произошла ошибка при получении статистики")

    async def cleanup_task(self):
        """Периодическая очистка старых записей"""
        try:
            await self.message_tracker.cleanup_old_records()
            logger.info("Cleanup task completed successfully")
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            
    # Функция-обертка для job_queue
    async def cleanup_task_wrapper(self, context):
        await self.cleanup_task()

    def __del__(self):
        """Закрываем сессию при удалении объекта"""
        if hasattr(self, 'session'):
            self.session.close()

async def setup_bot(application: Application):
    """Настройка бота перед запуском"""
    try:
        # Проверяем webhook
        webhook_info = await application.bot.get_webhook_info()
        if webhook_info.url:
            print(f"\n🔄 Удаляем существующий webhook: {webhook_info.url}")
            await application.bot.delete_webhook()
        
        # Проверяем права бота в канале
        try:
            # Проверка канала
            chat = await application.bot.get_chat(CHANNEL_ID)
            bot_member = await chat.get_member(application.bot.id)
            
            print(f"\n📢 Информация о канале:")
            print(f"• Название: {chat.title}")
            print(f"• Тип: {chat.type}")
            print(f"• ID: {chat.id}")
            
            print(f"\n🤖 Права бота в канале:")
            print(f"• Статус: {bot_member.status}")
            print(f"• Может читать сообщения: {bot_member.can_read_messages}")
            print(f"• Может удалять сообщения: {bot_member.can_delete_messages}")
            print(f"• Может отправлять сообщения: {bot_member.can_send_messages}")

            # Проверка группы обсуждений
            if DISCUSSION_GROUP_ID:
                try:
                    discussion_chat = await application.bot.get_chat(DISCUSSION_GROUP_ID)
                    discussion_member = await discussion_chat.get_member(application.bot.id)
                    
                    print(f"\n💬 Информация о группе обсуждений:")
                    print(f"• Название: {discussion_chat.title}")
                    print(f"• Тип: {discussion_chat.type}")
                    print(f"• ID: {discussion_chat.id}")
                    
                    print(f"\n🤖 Права бота в группе обсуждений:")
                    print(f"• Статус: {discussion_member.status}")
                    print(f"• Может читать сообщения: {discussion_member.can_read_messages}")
                    print(f"• Может удалять сообщения: {discussion_member.can_delete_messages}")
                    print(f"• Может отправлять сообщения: {discussion_member.can_send_messages}")
                except Exception as e:
                    print(f"\n❌ Ошибка при проверке группы обсуждений: {e}")
                    print("Убедитесь, что:")
                    print("1. Группа обсуждений создана и подключена к каналу")
                    print("2. Бот добавлен в группу как администратор")
                    print("3. ID группы указан верно")
            else:
                print("\n⚠️ ID группы обсуждений не указан")
                print("Для мониторинга комментариев необходимо:")
                print("1. Создать группу обсуждений для канала")
                print("2. Добавить бота администратором в группу")
                print("3. Указать DISCUSSION_GROUP_ID в файле .env")
            
        except Exception as e:
            print(f"\n❌ Ошибка при проверке канала: {e}")
            
        print("\n⚙️ Настройки бота:")
        print(f"• CHANNEL_ID: {CHANNEL_ID}")
        print(f"• DISCUSSION_GROUP_ID: {DISCUSSION_GROUP_ID}")
        print(f"• ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
        print(f"• Разрешенные обновления: channel_post, edited_channel_post, message, edited_message, callback_query")
        print(f"• Игнорирование старых обновлений: True")
        print(f"• Таймаут: 30 секунд")
        
    except Exception as e:
        print(f"\n❌ Ошибка при настройке бота: {e}")
        raise

def main():
    """Запуск бота"""
    nest_asyncio.apply()
    
    # Инициализация базы данных
    init_db()
    
    # Создание и настройка бота
    bot = HighLoadBot()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("stats", bot.show_stats))
    application.add_handler(CommandHandler("unban_user", bot.unban_user))
    application.add_handler(CommandHandler("get_chat_id", bot.get_chat_id))
    
    # Обработчики сообщений канала
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.UpdateType.CHANNEL_POST,
        bot.handle_comment,
        block=False
    ))
    
    # Обработчик редактирования сообщений канала
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.UpdateType.EDITED_CHANNEL_POST,
        bot.handle_edited_message,
        block=False
    ))
    
    # Обработчик комментариев в группе обсуждений
    if DISCUSSION_GROUP_ID:
        application.add_handler(MessageHandler(
            filters.Chat(chat_id=int(DISCUSSION_GROUP_ID)) & filters.TEXT,
            bot.handle_comment,
            block=False
        ))
        
        # Обработчик редактирования комментариев
        application.add_handler(MessageHandler(
            filters.Chat(chat_id=int(DISCUSSION_GROUP_ID)) & filters.UpdateType.EDITED_MESSAGE,
            bot.handle_edited_message,
            block=False
        ))
    
    # Обработчик обычных сообщений (не из канала)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.ChatType.CHANNEL,
        bot.handle_comment,
        block=False
    ))
    
    # Добавляем обработчик callback кнопок
    application.add_handler(CallbackQueryHandler(bot.handle_moderation_action))
    
    logging.info(
        f"Бот настроен для работы:\n"
        f"• CHANNEL_ID: {CHANNEL_ID} (тип: {type(CHANNEL_ID)})\n"
        f"• DISCUSSION_GROUP_ID: {DISCUSSION_GROUP_ID}\n"
        f"• ADMIN_CHAT_ID: {ADMIN_CHAT_ID}\n"
        f"• Разрешенные обновления: channel_post, edited_channel_post, message, edited_message, callback_query"
    )
    
    # Настройка и проверка бота перед запуском
    asyncio.get_event_loop().run_until_complete(setup_bot(application))
    
    # Запуск бота с разрешением всех типов обновлений
    application.run_polling(
        allowed_updates=[
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
            "callback_query"
        ],
        drop_pending_updates=True,
        timeout=30,
        read_timeout=30,
        write_timeout=30
    )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nБот остановлен.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Critical error: {e}")
        sys.exit(1) 