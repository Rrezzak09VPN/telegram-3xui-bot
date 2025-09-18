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

# Проверка/установка UFW
echo "🛡️ Проверка и установка UFW..."
if ! command -v ufw &> /dev/null; then
    echo "📥 UFW не найден, устанавливаем..."
    apt update
    apt install -y ufw
    echo "✅ UFW установлен"
else
    echo "✅ UFW уже установлен"
fi

# Включение UFW
echo "🔐 Включение UFW..."
ufw --force enable
systemctl start ufw
systemctl enable ufw
echo "✅ UFW включен и настроен на автозапуск"

# Настройка UFW (открытие стандартных портов)
# Примечание: SSH открыт по умолчанию. Закройте его через бота или вручную, если необходимо.
echo "🧱 Настройка UFW..."
ufw allow 22/tcp comment 'SSH'
ufw allow 443/tcp comment 'HTTPS'
echo "✅ Стандартные порты (22, 443) разрешены в UFW"

# Проверка версии Python
MIN_PYTHON_VERSION="3.7"
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")

if [[ "$(printf '%s\n' "$MIN_PYTHON_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$MIN_PYTHON_VERSION" ]]; then
    echo "❌ Требуется Python $MIN_PYTHON_VERSION или выше. Установлен Python $PYTHON_VERSION."
    echo "💡 Попробуйте установить Python $MIN_PYTHON_VERSION+: apt install python3.$MIN_PYTHON_VERSION-full python3.$MIN_PYTHON_VERSION-venv"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION подходит"

# Установка системных зависимостей
echo "📥 Установка системных зависимостей..."
apt install -y python3-pip python3-venv jq curl

# Создание структуры каталогов
echo "📂 Создание структуры каталогов..."
mkdir -p /opt/telegram-bot
mkdir -p /var/lib/telegram-bot
touch /var/log/telegram-bot.log
chmod 644 /var/log/telegram-bot.log

# Скачивание файлов проекта с GitHub
echo "🌐 Скачивание файлов проекта с GitHub..."
cd /opt/telegram-bot

# Скачиваем основные файлы
curl -sSL -o bot.py https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/bot.py
curl -sSL -o main.py https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/main.py
curl -sSL -o monitor.py https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/monitor.py
curl -sSL -o ssh_monitor.py https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/ssh_monitor.py
curl -sSL -o bot_ctl https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/bot_ctl
curl -sSL -o requirements.txt https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/requirements.txt
curl -sSL -o telegram-bot.service https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/src/telegram-bot.service

# Скачиваем пример конфига
mkdir -p /opt/telegram-bot/config
curl -sSL -o config/config.json.example https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/config/config.json.example

# Создание виртуального окружения и установка зависимостей
echo "🐍 Создание виртуального окружения и установка зависимостей..."
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

# Создание примера конфига в корне проекта, если его еще нет
if [ ! -f /opt/telegram-bot/config.json ]; then
    echo "📝 Создание примера конфигурационного файла..."
    cp /opt/telegram-bot/config/config.json.example /opt/telegram-bot/config.json
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
