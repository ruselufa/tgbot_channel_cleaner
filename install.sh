#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color
YELLOW='\033[1;33m'

# Функция для вывода сообщений
print_message() {
    echo -e "${GREEN}[+] $1${NC}"
}

print_error() {
    echo -e "${RED}[!] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

# Проверка наличия Python 3.10 или выше
check_python() {
    if command -v python3 >/dev/null 2>&1; then
        python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if (( $(echo "$python_version 3.10" | awk '{print ($1 >= $2)}') )); then
            print_message "Python $python_version найден"
            return 0
        fi
    fi
    
    print_error "Python 3.10 или выше не найден"
    
    # Установка Python в зависимости от ОС
    if [[ "$OSTYPE" == "darwin"* ]]; then
        print_message "Установка Python для macOS..."
        if command -v brew >/dev/null 2>&1; then
            brew install python@3.10
        else
            print_error "Homebrew не установлен. Установите Python 3.10 вручную"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        print_message "Установка Python для Linux..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update
            sudo apt-get install -y python3.10 python3.10-venv
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y python3.10 python3.10-devel
        else
            print_error "Неподдерживаемый дистрибутив Linux. Установите Python 3.10 вручную"
            exit 1
        fi
    else
        print_error "Неподдерживаемая операционная система"
        exit 1
    fi
}

# Создание и активация виртуального окружения
setup_venv() {
    print_message "Создание виртуального окружения..."
    if [ -d "venv" ]; then
        print_warning "Виртуальное окружение уже существует. Удаляем..."
        rm -rf venv
    fi
    python3 -m venv venv
    
    # Активация виртуального окружения
    source venv/bin/activate || source venv/Scripts/activate
    
    print_message "Обновление pip..."
    pip install --upgrade pip
}

# Установка зависимостей
install_dependencies() {
    print_message "Установка зависимостей..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        print_error "Файл requirements.txt не найден"
        exit 1
    fi
}

# Проверка наличия .env файла
check_env() {
    print_message "Проверка конфигурации..."
    if [ ! -f ".env" ]; then
        print_warning ".env файл не найден. Создаю пример..."
        cat > .env << EOL
# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here
CHANNEL_ID=your_channel_id_here
DISCUSSION_GROUP_ID=your_discussion_group_id_here
ADMIN_CHAT_ID=your_admin_chat_id_here

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Text Analysis Models
BERT_MODEL_PATH=blanchefort/rubert-base-cased-sentiment
TOXIC_MODEL_PATH=SkolkovoInstitute/russian_toxicity_classifier
EMOTION_MODEL_PATH=Aniemore/rubert-tiny2-russian-emotion-detection

# Warning System
MAX_WARNINGS=3
BAN_DURATION_HOURS=24

# Thresholds
NEGATIVE_THRESHOLD=0.7
TOXICITY_THRESHOLD=0.8
EMOTION_THRESHOLD=0.7

# Monitoring
PROMETHEUS_PORT=8000
EOL
        print_warning "Пожалуйста, отредактируйте .env файл перед запуском бота"
    fi
}

# Основной процесс установки
main() {
    print_message "Начало установки..."
    
    check_python
    setup_venv
    install_dependencies
    check_env
    
    print_message "Установка завершена успешно!"
    print_message "Для запуска бота активируйте виртуальное окружение:"
    print_message "source venv/bin/activate  # для Linux/macOS"
    print_message "venv\\Scripts\\activate  # для Windows"
    print_message "Затем запустите бота:"
    print_message "python src/bot.py"
}

# Запуск установки
main 