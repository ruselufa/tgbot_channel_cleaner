import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DISCUSSION_GROUP_ID = os.getenv('DISCUSSION_GROUP_ID')  # ID группы обсуждений канала

# Database Configuration
DB_HOST = os.getenv('DB_HOST', 'master.ddb2bc2c-b9c8-4cd7-bafd-8b21e116dcdf.c.dbaas.selcloud.ru')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'amber')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'VZizwWS8NPgu')
DB_NAME = os.getenv('DB_NAME', 'tgbot_moderator')
DB_SSL_MODE = os.getenv('DB_SSL_MODE', 'disable')

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode={DB_SSL_MODE}"

# Redis Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

# Moderation Settings
MAX_WARNINGS = int(os.getenv('MAX_WARNINGS', '3'))
BAN_DURATION = int(os.getenv('BAN_DURATION', '24'))  # 24 часа вместо 86400 секунд
NEGATIVE_THRESHOLD = float(os.getenv('NEGATIVE_THRESHOLD', '-0.3'))
MESSAGE_TRACKING_DAYS = int(os.getenv('MESSAGE_TRACKING_DAYS', '7'))

# Performance Settings
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '32'))
WORKER_COUNT = int(os.getenv('WORKER_COUNT', '4'))
CACHE_TTL = int(os.getenv('CACHE_TTL', '3600'))

# Negative words list (можно расширить)
NEGATIVE_WORDS = [
    'плохо', 'ужасно', 'отстой', 'мусор', 'говно', 'дерьмо',
    'хрень', 'фигня', 'дрянь', 'отвратительно', 'ненавижу',
    'тупой', 'идиот', 'дебил', 'урод', 'мразь', 'тварь',
    'отморозок', 'скотина', 'сволочь', 'придурок'
]

# Warning messages
MESSAGES = {
    'comment_on_moderation': 'Ваш комментарий отправлен на модерацию. После проверки он будет опубликован.',
    'comment_approved': '✅ Ваш комментарий был одобрен модератором.',
    'comment_rejected': '❌ Ваш комментарий был отклонен модератором.\nПричина: {}',
    'user_warning': '⚠️ Вы получили предупреждение за {}.\nУ вас {} предупреждений из {}.',
    'user_banned': '🚫 Вы были заблокированы на {} часов за нарушение правил.',
    'user_in_blacklist': 'Вы находитесь в черном списке и не можете оставлять комментарии.',
    'suspicious_edit': 'Ваше изменение комментария было отклонено как подозрительное. Причина: {}',
    'edit_banned': 'Изменение комментариев временно заблокировано для вашего аккаунта.',
    'user_blacklisted': '⛔️ Вы были добавлены в черный список за многократные нарушения.'
}

# Model paths
BERT_MODEL_PATH = os.getenv('BERT_MODEL_PATH', 'DeepPavlov/rubert-base-cased-sentiment')
TOXIC_MODEL_PATH = os.getenv('TOXIC_MODEL_PATH', 'cointegrated/rubert-tiny2-toxic')
EMOTION_MODEL_PATH = os.getenv('EMOTION_MODEL_PATH', 'cointegrated/rubert-tiny2-emotion') 