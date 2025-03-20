import logging
from datetime import datetime, timedelta
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from models import Session, init_db
from services import UserService, CommentService, ModeratorLogService
from core.text_analyzer import TextAnalyzer
from core.message_tracker import MessageTracker
from core.message_broker import MessageBroker
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
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Привет! Я бот-модератор. Я буду следить за комментариями в канале и помогать с модерацией."
        )

    async def handle_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.reply_to_message:
            return
            
        session = Session()
        try:
            # Инициализация сервисов
            user_service = UserService(session)
            comment_service = CommentService(session)
            log_service = ModeratorLogService(session)
            
            # Получаем или создаем пользователя
            user = user_service.get_or_create_user(
                update.message.from_user.id,
                update.message.from_user.username
            )
            
            # Проверяем ограничения пользователя
            can_comment, restriction_reason = user_service.check_user_restrictions(user)
            if not can_comment:
                await update.message.reply_text(restriction_reason)
                return
                
            # Анализируем текст комментария
            is_negative, sentiment_score, analysis = await self.text_analyzer.is_negative(update.message.text)
            
            # Создаем комментарий в базе
            comment = comment_service.create_comment(
                user=user,
                post_id=update.message.reply_to_message.message_id,
                text=update.message.text,
                sentiment_score=sentiment_score
            )
            
            # Если комментарий негативный, автоматически отклоняем его
            if is_negative:
                reason = self.text_analyzer.get_toxicity_reason(analysis)
                comment_service.reject_comment(comment, None, reason)
                
                # Добавляем предупреждение пользователю
                warnings_count, should_ban = user_service.add_warning(user, reason)
                
                # Логируем действие
                log_service.log_action(
                    moderator_id=None,
                    action='auto_reject_comment',
                    target_user_id=user.telegram_id,
                    comment_id=comment.id,
                    details=reason,
                    analysis_data=analysis
                )
                
                # Отправляем уведомление пользователю
                await update.message.reply_text(
                    MESSAGES['comment_rejected'].format(reason)
                )
                
                if should_ban:
                    await update.message.reply_text(
                        MESSAGES['user_banned'].format(24)
                    )
                else:
                    await update.message.reply_text(
                        MESSAGES['user_warning'].format(
                            reason, warnings_count, MAX_WARNINGS
                        )
                    )
            else:
                # Начинаем отслеживание сообщения
                await self.message_tracker.track_message(
                    message_id=update.message.message_id,
                    text=update.message.text,
                    sentiment_score=sentiment_score,
                    user_id=user.telegram_id,
                    username=user.username
                )
                
                # Отправляем комментарий на модерацию
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{comment.id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{comment.id}")
                    ]
                ]
                markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(
                        f"Новый комментарий от @{update.message.from_user.username}\n"
                        f"К посту: {comment.post_id}\n"
                        f"Текст: {comment.text}\n"
                        f"Оценка тональности: {sentiment_score:.2f}"
                    ),
                    reply_markup=markup
                )
                
                await update.message.reply_text(MESSAGES['comment_on_moderation'])
                
        except Exception as e:
            logger.error(f"Error handling comment: {e}")
            await update.message.reply_text("Произошла ошибка при обработке комментария.")
        finally:
            session.close()

    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка измененных сообщений"""
        message = update.edited_message
        if not message.reply_to_message:
            return
            
        session = Session()
        try:
            user_service = UserService(session)
            comment_service = CommentService(session)
            log_service = ModeratorLogService(session)
            
            # Получаем пользователя
            user = user_service.get_or_create_user(
                message.from_user.id,
                message.from_user.username
            )
            
            # Проверяем ограничения на редактирование
            can_edit, restriction_reason = user_service.check_edit_restrictions(user)
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
                    user_service.update_suspicious_edits_count(user)
                    
                    # Записываем изменение в базу
                    comment = session.query(Comment).filter_by(
                        post_id=message.reply_to_message.message_id,
                        user_id=user.id
                    ).first()
                    
                    if comment:
                        edit = comment_service.record_edit(
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
        finally:
            session.close()

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

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        session = Session()
        try:
            log_service = ModeratorLogService(session)
            
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
        finally:
            session.close()

    async def cleanup_task(self):
        """Периодическая очистка старых записей"""
        while True:
            try:
                await self.message_tracker.cleanup_old_records()
                await asyncio.sleep(3600)  # Раз в час
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(300)  # При ошибке ждем 5 минут

async def main():
    # Инициализация базы данных
    init_db()
    
    # Создание бота
    bot = HighLoadBot()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("stats", bot.show_stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_comment))
    application.add_handler(MessageHandler(filters.TEXT & filters.UpdateType.EDITED_MESSAGE, bot.handle_edited_message))
    application.add_handler(CallbackQueryHandler(bot.handle_moderation_action))
    
    # Запуск фоновых задач
    asyncio.create_task(bot.cleanup_task())
    
    # Запуск бота
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main()) 