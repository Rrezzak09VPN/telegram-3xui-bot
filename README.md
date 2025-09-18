# 🤖 Telegram Bot для управления 3X-UI

Этот бот предоставляет удобный способ управления доступом к веб-панели 3X-UI и мониторинга сервера через Telegram.

## 🌟 Функционал

- **Управление доступом к панели:**
  - `/getlink` - Получить временную ссылку на панель (порт открывается на заданное время)
  - `/offlink` - Закрыть доступ к панели (порт закрывается вручную)
- **Мониторинг:**
  - `/status` - Получить статус сервера и ресурсов
  - Автоматические уведомления о статусе сервера и 3X-UI
  - Мониторинг SSH подключений с геоинформацией
- **Настройка:**
  - `/change_config` - Изменить настройки бота (время доступа, URL панели, порт панели)
- **Управление SSH:**
  - `/open_ssh` - Открыть SSH порт (22) на 1 час (можно накапливать)
  - `/close_ssh` - Закрыть SSH порт (22)

## 🛠️ Установка

### Предварительные требования

- Чистый сервер с Ubuntu
- Установленная 3X-UI панель
- Активный Telegram бот (получите токен через @BotFather)
- Ваш Telegram Chat ID (узнайте через @userinfobot или другие способы)

### Шаги установки

1. **Скачайте и запустите скрипт установки:**
   \`\`\`bash wget -O - https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/scripts/install.sh | bash
   \`\`\`
   или
   \`\`\`bash
   curl -sSL https://raw.githubusercontent.com/Rrezzak09VPN/telegram-3xui-bot/main/scripts/install.sh | bash
   \`\`\`

2. **Настройте конфигурационный файл:**
   После установки отредактируйте \`/opt/telegram-bot/config.json\`:
   \`\`\`bash
   nano /opt/telegram-bot/config.json
   \`\`\`
   
   Заполните следующие поля:
   - \`telegram_token\`: Токен вашего Telegram бота (получается у @BotFather)
   - \`owner_chat_id\`: Ваш Telegram Chat ID (узнать можно через @userinfobot)
   - \`panel_port\`: Порт вашей 3X-UI панели (целое число от 1 до 65535)
   - \`panel_url\`: Полный URL вашей 3X-UI панели (например, \`http://ваш_IP:порт/путь\`)

3. **Запустите бота:**
   \`\`\`bash
   systemctl start telegram-bot.service
   \`\`\`

4. **Проверьте статус:**
   \`\`\`bash
   systemctl status telegram-bot.service
   \`\`\`

5. **(Опционально) Включите автозапуск:**
   \`\`\`bash
   systemctl enable telegram-bot.service
   \`\`\`

## 📋 Управление ботом

Вы можете управлять ботом через вспомогательный скрипт \`/opt/telegram-bot/bot_ctl\`:

\`\`\`bash
# Запуск
/opt/telegram-bot/bot_ctl start

# Остановка
/opt/telegram-bot/bot_ctl stop

# Перезапуск
/opt/telegram-bot/bot_ctl restart

# Просмотр статуса
/opt/telegram-bot/bot_ctl status

# Просмотр логов в реальном времени
/opt/telegram-bot/bot_ctl logs
\`\`\`

## 📂 Структура проекта

- \`/opt/telegram-bot/\` - Основной каталог бота
- \`/opt/telegram-bot/config.json\` - Конфигурационный файл
- \`/opt/telegram-bot/venv/\` - Виртуальное окружение Python
- \`/var/log/telegram-bot.log\` - Лог-файл бота
- \`/var/lib/telegram-bot/state.json\` - Файл состояния для мониторинга перезагрузок
- \`/etc/systemd/system/telegram-bot.service\` - Сервисный файл systemd

## 📄 Лицензия

MIT License
