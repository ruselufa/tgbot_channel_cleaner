import logging
from datetime import datetime, timedelta
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, Defaults

from src.models import Session, User, Comment
from src.db.init_db import init_db
from src.services import UserService, CommentService, ModeratorLogService
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
        
    async def handle_moderation_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка действий модерации (кнопки одобрения/отклонения)"""
        query = update.callback_query
        await query.answer()
        
        # Получаем данные из callback_data
        action, comment_id = query.data.split('_')
        comment_id = int(comment_id)
        
        session = Session()
        try:
            # Инициализация сервисов
            comment_service = CommentService(session)
            user_service = UserService(session)
            log_service = ModeratorLogService(session)
            
            # Получаем комментарий
            comment = session.query(Comment).filter_by(id=comment_id).first()
            if not comment:
                await query.edit_message_text("Комментарий не найден")
                return
                
            # Получаем пользователя
            user = session.query(User).filter_by(id=comment.user_id).first()
            
            if action == "approve":
                # Одобряем комментарий
                comment_service.approve_comment(comment, query.from_user.id)
                
                # Логируем действие
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
                comment_service.reject_comment(comment, query.from_user.id, reason)
                
                # Добавляем предупреждение пользователю
                warnings_count, should_ban = user_service.add_warning(user, reason)
                
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
        finally:
            session.close()

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
        try:
            await self.message_tracker.cleanup_old_records()
            logger.info("Cleanup task completed successfully")
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            
    # Функция-обертка для job_queue
    async def cleanup_task_wrapper(self, context):
        await self.cleanup_task()

if __name__ == "__main__":
    try:
        # Инициализация базы данных
        init_db()
        
        # Создание бота
        bot = HighLoadBot()
        
        # Настраиваем аргументы для бота
        defaults = Defaults(parse_mode=ParseMode.HTML)  # Форматирование сообщений по умолчанию
        
        # Построитель приложения с новыми настройками
        builder = Application.builder()
        builder.token(BOT_TOKEN)
        builder.defaults(defaults)
        
        # Построение приложения
        application = builder.build()
        
        # Добавление обработчиков
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("stats", bot.show_stats))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_comment))
        application.add_handler(MessageHandler(filters.TEXT & filters.UpdateType.EDITED_MESSAGE, bot.handle_edited_message))
        application.add_handler(CallbackQueryHandler(bot.handle_moderation_action))
        
        logger.info("Бот запускается...")
        print("Бот запущен. Нажмите Ctrl+C для остановки.")
        
        # Синхронный запуск бота
        application.run_polling()
        
    except KeyboardInterrupt:
        print("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        print(f"Произошла ошибка: {e}") 