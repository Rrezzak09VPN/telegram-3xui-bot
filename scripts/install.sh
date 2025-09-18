#!/bin/bash

# Telegram Bot for 3X-UI Installation Script

set -e # Exit on any error

echo "🚀 Начинаем установку Telegram Bot для 3X-UI..."

# Проверка ОС
if ! grep -q Ubuntu /etc/os-release; then
    echo "❌ Скрипт поддерживает только Ubuntu"
    exit 1
fi

echo "✅ ОС Ubuntu подтверждена"

# Проверка, что мы под root
if [[ $EUID -ne 0 ]]; then
   echo "❌ Этот скрипт должен быть запущен под root"
   exit 1
fi

echo "✅ Запущен под root"

# Установка зависимостей
echo "📥 Установка системных зависимостей..."
apt update
apt install -y python3 python3-pip python3-venv ufw jq curl

# Настройка UFW (открытие стандартных портов)
echo "🛡️ Настройка UFW..."
ufw allow 22/tcp comment 'SSH'
ufw allow 443/tcp comment 'HTTPS'
echo "✅ Стандартные порты (22, 443) разрешены в UFW"

# Создание структуры каталогов
echo "📂 Создание структуры каталогов..."
mkdir -p /opt/telegram-bot
mkdir -p /var/lib/telegram-bot
touch /var/log/telegram-bot.log
chmod 644 /var/log/telegram-bot.log

# Копирование файлов проекта
echo "📋 Копирование файлов проекта..."
cp -r src/* /opt/telegram-bot/

# Создание виртуального окружения и установка зависимостей
echo "🐍 Создание виртуального окружения и установка зависимостей..."
cd /opt/telegram-bot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Настройка прав доступа
echo "🔐 Настройка прав доступа..."
chmod +x /opt/telegram-bot/bot.py
chmod +x /opt/telegram-bot/main.py
chmod +x /opt/telegram-bot/monitor.py
chmod +x /opt/telegram-bot/ssh_monitor.py
chmod +x /opt/telegram-bot/bot_ctl

# Копирование и настройка systemd сервиса
echo "⚙️ Настройка systemd сервиса..."
cp /opt/telegram-bot/telegram-bot.service /etc/systemd/system/
systemctl daemon-reload

# Создание примера конфига, если его еще нет
if [ ! -f /opt/telegram-bot/config.json ]; then
    echo "📝 Создание примера конфигурационного файла..."
    cp ../config/config.json.example /opt/telegram-bot/config.json
    echo "⚠️  ВНИМАНИЕ: Вы должны отредактировать /opt/telegram-bot/config.json"
    echo "⚠️  и ввести ваши данные (токен бота, chat_id, порт и URL панели)"
fi

echo "✅ Установка завершена!"

echo "
📋 Дальнейшие шаги:
1. Отредактируйте конфигурационный файл:
   nano /opt/telegram-bot/config.json
   
   Заполните следующие поля:
   - telegram_token: Токен вашего Telegram бота
   - owner_chat_id: Ваш Telegram Chat ID
   - panel_port: Порт вашей 3X-UI панели (целое число от 1 до 65535)
   - panel_url: Полный URL вашей 3X-UI панели

2. После настройки конфига запустите бота:
   systemctl start telegram-bot.service

3. Проверьте статус:
   systemctl status telegram-bot.service

4. Для просмотра логов:
   journalctl -u telegram-bot.service -f

5. Для автоматического запуска после перезагрузки:
   systemctl enable telegram-bot.service

🎉 Готово! Бот установлен и готов к работе.
"

