import logging
from datetime import datetime, timedelta
import asyncio
import sys
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    MAX_WARNINGS, WORKER_COUNT
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
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
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Привет! Я бот-модератор. Я буду следить за комментариями в канале и помогать с модерацией."
        )

    async def handle_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка комментария"""
        try:
            # Проверяем, откуда пришло сообщение
            message = update.message or update.edited_message or update.channel_post
            if not message or not message.text:
                return
                
            # Проверяем, что сообщение из нужного канала
            if message.chat.id != int(CHANNEL_ID):
                logging.info(f"Сообщение не из целевого канала. ID чата: {message.chat.id}")
                return
                
            user_id = message.from_user.id if message.from_user else None
            if not user_id:
                logging.warning("Не удалось получить ID пользователя")
                return
                
            text = message.text
            
            # Анализ текста
            is_negative = await self.text_analyzer.is_negative(text)
            toxicity_score = await self.text_analyzer.get_toxicity_score(text)
            emotion = await self.text_analyzer.get_emotion(text)
            
            logging.info(f"Text analysis results: negative={is_negative}, toxic={toxicity_score}, emotion={emotion}")
            
            # Проверка на негативный контент
            if is_negative:
                try:
                    # Получаем пользователя и добавляем предупреждение
                    user = await self.user_service.get_or_create_user(user_id, message.from_user.username)
                    warnings_count = await self.user_service.add_warning(user_id)
                    
                    if warnings_count >= MAX_WARNINGS:
                        # Баним пользователя
                        try:
                            await context.bot.delete_message(
                                chat_id=message.chat.id,
                                message_id=message.message_id
                            )
                            await context.bot.send_message(
                                chat_id=message.chat.id,
                                text=f"Пользователь @{message.from_user.username} заблокирован за нарушение правил."
                            )
                        except Exception as e:
                            logging.error(f"Ошибка при удалении сообщения или бане пользователя: {e}")
                    else:
                        # Отправляем предупреждение
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"⚠️ Предупреждение! Ваше сообщение содержит негативный контент.\nУ вас {warnings_count} предупреждений из {MAX_WARNINGS}."
                            )
                        except Exception as e:
                            logging.error(f"Ошибка при отправке предупреждения пользователю: {e}")
                    
                    # Уведомление администраторов
                    if ADMIN_CHAT_ID:
                        try:
                            await context.bot.send_message(
                                chat_id=ADMIN_CHAT_ID,
                                text=f"🚨 Негативное сообщение от @{message.from_user.username}:\n\n{text}\n\n"
                                    f"Анализ:\n"
                                    f"- Негативность: {is_negative}\n"
                                    f"- Токсичность: {toxicity_score:.2f}\n"
                                    f"- Эмоция: {emotion}\n"
                                    f"- Предупреждений: {warnings_count}/{MAX_WARNINGS}"
                            )
                        except Exception as e:
                            logging.error(f"Error sending message to admin chat: {e}")
                except Exception as e:
                    logging.error(f"Error processing warning: {e}")
                    traceback.print_exc()
                        
        except Exception as e:
            logging.error(f"Error processing negative comment: {e}")
            traceback.print_exc()
        finally:
            self.session.commit()

    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка измененных сообщений"""
        message = update.edited_message
        if not message.reply_to_message:
            return
            
        try:
            # Получаем пользователя
            user = self.user_service.get_or_create_user(
                message.from_user.id,
                message.from_user.username
            )
            
            # Проверяем ограничения на редактирование
            can_edit, restriction_reason = self.user_service.check_edit_restrictions(user)
            if not can_edit:
                await message.reply_text(restriction_reason)
                await message.delete()
                return
            
            # Проверяем изменение
            check_result = await self.message_tracker.check_edit(
                message.message_id,
                message.text
            )
            
            if not check_result:
                return
                
            if check_result['is_suspicious']:
                try:
                    # Обновляем счетчик подозрительных изменений
                    self.user_service.update_suspicious_edits_count(user)
                    
                    # Записываем изменение в базу
                    comment = self.session.query(Comment).filter_by(
                        post_id=message.reply_to_message.message_id,
                        user_id=user.id
                    ).first()
                    
                    if comment:
                        edit = self.comment_service.record_edit(
                            comment=comment,
                            new_text=message.text,
                            sentiment_change=check_result['edit_info']['sentiment_change'],
                            is_suspicious=True,
                            analysis_data=check_result['edit_info']['analysis']
                        )
                    
                    # Удаляем подозрительное сообщение
                    await context.bot.delete_message(
                        chat_id=message.chat_id,
                        message_id=message.message_id
                    )
                    
                    # Уведомляем пользователя
                    await context.bot.send_message(
                        chat_id=message.from_user.id,
                        text=MESSAGES['suspicious_edit'].format(
                            self.text_analyzer.get_toxicity_reason(
                                check_result['edit_info']['analysis']
                            )
                        )
                    )
                    
                    # Логируем инцидент
                    log_service = ModeratorLogService(self.session)
                    log_service.log_action(
                        moderator_id=None,
                        action='suspicious_edit',
                        target_user_id=user.telegram_id,
                        comment_id=comment.id if comment else None,
                        details=str(check_result['edit_info']),
                        analysis_data=check_result['edit_info']['analysis']
                    )
                    
                    # Уведомляем модераторов
                    await self._notify_moderators_about_edit(message, check_result['edit_info'])
                    
                except Exception as e:
                    logger.error(f"Error handling suspicious edit: {e}")
                    
        except Exception as e:
            logger.error(f"Error in handle_edited_message: {e}")

    async def _notify_moderators_about_edit(self, message, edit_info):
        """Уведомление модераторов о подозрительном изменении"""
        notification = (
            f"🚨 Обнаружено подозрительное изменение сообщения\n\n"
            f"Пользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
            f"Оригинальный текст:\n{edit_info['old_text']}\n\n"
            f"Измененный текст:\n{edit_info['new_text']}\n\n"
            f"Изменение тональности: {edit_info['sentiment_change']:.2f}\n"
            f"Причина блокировки: {self.text_analyzer.get_toxicity_reason(edit_info['analysis'])}\n"
            f"Сообщение удалено автоматически."
        )
        
        await self.message_broker.push_message({
            'chat_id': ADMIN_CHAT_ID,
            'text': notification,
            'priority': True
        })
        
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

def main():
    """Основная функция запуска бота"""
    try:
        # Применяем патч для вложенных event loops
        nest_asyncio.apply()
        
        # Настройка логирования
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        
        # Инициализация бота
        defaults = Defaults(parse_mode=ParseMode.HTML)
        application = Application.builder().token(BOT_TOKEN).defaults(defaults).build()
        bot = HighLoadBot()
        
        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("stats", bot.show_stats))
        
        # Регистрация обработчиков сообщений для канала и обычных чатов
        application.add_handler(MessageHandler(
            (filters.TEXT | filters.CAPTION | filters.UpdateType.CHANNEL_POST) & ~filters.COMMAND, 
            bot.handle_comment
        ))
        
        # Регистрация обработчика изменений сообщений
        application.add_handler(MessageHandler(
            filters.UpdateType.EDITED_MESSAGE | filters.UpdateType.EDITED_CHANNEL_POST,
            bot.handle_edited_message
        ))
        
        # Регистрация обработчика callback-кнопок
        application.add_handler(CallbackQueryHandler(bot.handle_moderation_action))
        
        # Добавляем задачу очистки
        job_queue = application.job_queue
        job_queue.run_repeating(bot.cleanup_task_wrapper, interval=timedelta(hours=24))
        
        # Запуск бота
        logging.info("Бот запускается...")
        print("Бот запущен. Нажмите Ctrl+C для остановки.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logging.error(f"Error starting bot: {e}")
        raise

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nБот остановлен.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Critical error: {e}")
        sys.exit(1) 