#!/usr/bin/env python3

import json
import logging
import threading
import time
import subprocess
import requests
import urllib3
import psutil
import os
import re
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, Filters

# Загрузка конфигурации
with open('config.json', 'r') as f:
    config = json.load(f)

# Настройка логирования
logging.basicConfig(
    filename=config['log_file'],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные для отслеживания состояния
active_session = False
session_timer = None

# === Глобальные переменные для /change_config ===
# Состояние ожидания ввода: None или ключ конфига ('access_duration_minutes', 'panel_url', 'panel_port')
awaiting_input_for = None
# ID чата владельца, который инициировал изменение (для безопасности)
change_config_initiator_chat_id = None

# === Глобальные переменные для SSH ===
ssh_timer = None  # Таймер для автоматического закрытия SSH
ssh_open_count = 0  # Счетчик вызовов /open_ssh для накопления времени

def get_size(bytes, suffix="B"):
    """Масштабировать байты в надлежащие единицы измерения"""
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor
    return f"{bytes:.2f}Y{suffix}"

def get_uptime_string():
    """Получить строку аптайма"""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        if days > 0:
            return f"{days} дней, {hours} часов, {minutes} минут"
        elif hours > 0:
            return f"{hours} часов, {minutes} минут"
        else:
            return f"{minutes} минут"
    except Exception as e:
        return f"Ошибка получения аптайма: {e}"

def log_message(message):
    """Функция для логирования сообщений"""
    logger.info(message)
    print(message)

def check_server_status():
    """Проверка доступности сервера"""
    try:
        # Простая проверка - сервер онлайн если мы можем получить uptime
        with open('/proc/uptime', 'r') as f:
            uptime = f.read()
        return True
    except:
        return False

def check_xui_status():
    """Проверка статуса x-ui сервиса"""
    try:
        result = subprocess.run(['systemctl', 'is-active', 'x-ui'],
                              capture_output=True, text=True, timeout=10)
        return result.stdout.strip() == 'active'
    except:
        return False

def open_panel_port(port):
    """Открытие порта панели через UFW"""
    try:
        subprocess.run(['ufw', 'allow', str(port)], check=True, capture_output=True)
        log_message(f"Порт {port} (панель) открыт")
        return True
    except Exception as e:
        log_message(f"Ошибка открытия порта {port} (панель): {e}")
        return False

def close_panel_port(port):
    """Закрытие порта панели через UFW"""
    try:
        subprocess.run(['ufw', 'deny', str(port)], check=True, capture_output=True)
        log_message(f"Порт {port} (панель) закрыт")
        return True
    except Exception as e:
        log_message(f"Ошибка закрытия порта {port} (панель): {e}")
        return False

def open_ssh_port():
    """Открытие SSH порта (22) через UFW"""
    try:
        subprocess.run(['ufw', 'allow', '22'], check=True, capture_output=True)
        log_message("SSH порт (22) открыт")
        return True
    except Exception as e:
        log_message(f"Ошибка открытия SSH порта (22): {e}")
        return False

def close_ssh_port():
    """Закрытие SSH порта (22) через UFW"""
    try:
        subprocess.run(['ufw', 'deny', '22'], check=True, capture_output=True)
        log_message("SSH порт (22) закрыт")
        return True
    except Exception as e:
        log_message(f"Ошибка закрытия SSH порта (22): {e}")
        return False

def end_session(bot):
    """Функция завершения сессии панели"""
    global active_session
    close_panel_port(config['panel_port'])
    active_session = False
    # Отправляем сообщение владельцу о завершении сессии
    try:
        bot.send_message(
            chat_id=config['owner_chat_id'],
            text="⚠️ Сессия доступа к панели завершена. Порт закрыт."
        )
    except Exception as e:
        log_message(f"Ошибка отправки уведомления о завершении сессии панели: {e}")

def end_ssh_session(bot):
    """Функция завершения SSH сессии (закрытие порта)"""
    global ssh_timer, ssh_open_count
    if close_ssh_port():
        try:
            bot.send_message(
                chat_id=config['owner_chat_id'],
                text="🔒 SSH порт (22) автоматически закрыт по истечении времени."
            )
        except Exception as e:
            log_message(f"Ошибка отправки уведомления о закрытии SSH порта: {e}")
    else:
        log_message("Не удалось автоматически закрыть SSH порт (22)")
    
    # Сброс состояния SSH
    ssh_timer = None
    ssh_open_count = 0

def set_bot_commands(bot):
    """Устанавливаем команды для меню бота (все в нижнем регистре)"""
    try:
        # Определяем список команд в правильном формате (все в нижнем регистре!)
        commands = [
            ("start", "Главное меню"),
            ("help", "Помощь по боту"),
            ("getlink", "Получить ссылку на панель"),
            ("offlink", "Закрыть доступ к панели"),
            ("status", "Статус сервера и ресурсов"),
            ("change_config", "Изменить настройки бота"),
            ("open_ssh", "Открыть SSH порт (22)"),
            ("close_ssh", "Закрыть SSH порт (22)")
        ]
        
        # Отправляем запрос Telegram API
        result = bot.set_my_commands(commands)
        if result:
            log_message("✅ Меню бота успешно установлено.")
        else:
            log_message("❌ Не удалось установить меню бота (set_my_commands вернул False).")
    except Exception as e:
        log_message(f"❌ Ошибка при установке меню бота: {e}")

# ==================== НОВЫЕ ФУНКЦИИ ДЛЯ /change_config ====================

def validate_url(url):
    """
    Проверяет корректность URL панели и извлекает порт.
    Возвращает (is_valid, port, error_message)
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, None, "Некорректный формат URL. Должен начинаться с http:// или https://"
        
        if parsed.scheme not in ['http', 'https']:
            return False, None, "URL должен начинаться с http:// или https://"
            
        # Проверяем, есть ли порт в URL
        if ':' in parsed.netloc:
            host, port_str = parsed.netloc.rsplit(':', 1)
            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    return False, None, "Порт должен быть числом от 1 до 65535"
                return True, port, None
            except ValueError:
                return False, None, "Некорректный номер порта в URL"
        else:
            # Если порт не указан, используем стандартные
            port = 80 if parsed.scheme == 'http' else 443
            return True, port, None
            
    except Exception as e:
        return False, None, f"Ошибка при разборе URL: {e}"

def validate_port(port_str):
    """
    Проверяет корректность порта.
    Возвращает (is_valid, port, error_message)
    """
    try:
        port = int(port_str)
        if not (1 <= port <= 65535):
            return False, None, "Порт должен быть числом от 1 до 65535"
            
        # Проверка на "опасные" порты
        dangerous_ports = [22, 443]
        if port in dangerous_ports:
            return False, None, f"Порт {port} зарезервирован и не может быть использован как порт панели."
            
        if port == config['panel_port']:
            return False, None, "Новый порт совпадает с текущим. Введите другой порт."
        return True, port, None
    except ValueError:
        return False, None, "Порт должен быть числом"

def validate_duration(duration_str):
    """
    Проверяет корректность времени доступа.
    Возвращает (is_valid, minutes, error_message)
    """
    try:
        minutes = int(duration_str)
        if minutes <= 0:
            return False, None, "Время должно быть положительным числом"
        if minutes > 1440: # 24 часа
            return False, None, "Время не должно превышать 1440 минут (24 часа)"
        return True, minutes, None
    except ValueError:
        return False, None, "Время должно быть числом (в минутах)"

def update_config_file(key, new_value):
    """
    Безопасно обновляет значение в config.json
    """
    try:
        # Читаем текущий конфиг
        with open('config.json', 'r') as f:
            current_config = json.load(f)
        
        # Обновляем значение
        old_value = current_config.get(key)
        current_config[key] = new_value
        
        # Записываем обновленный конфиг
        with open('config.json', 'w') as f:
            json.dump(current_config, f, indent=4)
            
        log_message(f"✅ Конфиг обновлен: {key} изменен с '{old_value}' на '{new_value}'")
        return True
    except Exception as e:
        error_msg = f"❌ Ошибка при обновлении конфига: {e}"
        log_message(error_msg)
        return False

def apply_port_change(old_port, new_port):
    """
    Закрывает старый порт, если он открыт (ALLOW).
    Улучшенная версия с точной проверкой.
    """
    try:
        # Проверяем, открыт ли старый порт (ищем точное совпадение с ALLOW)
        result = subprocess.run(['ufw', 'status'], capture_output=True, text=True, timeout=10)
        
        # Ищем строку вида "14698 ALLOW Anywhere" или "14698/tcp ALLOW Anywhere"
        # Это более надежный способ, чем просто проверка наличия числа в выводе
        pattern = re.compile(rf'^\s*{old_port}(/tcp)?\s+ALLOW\s+', re.MULTILINE)
        
        if pattern.search(result.stdout):
            # Порт открыт (ALLOW), закрываем его
            if close_panel_port(old_port):
                log_message(f"✅ Старый порт {old_port} закрыт")
                return True
            else:
                log_message(f"❌ Не удалось закрыть старый порт {old_port}")
                return False
        else:
            log_message(f"ℹ️ Старый порт {old_port} не был открыт (ALLOW), закрывать не нужно")
            return True
    except Exception as e:
        log_message(f"❌ Ошибка при проверке/закрытии старого порта: {e}")
        return False

def change_config_command(update: Update, context: CallbackContext):
    """Обработка команды /change_config"""
    if update.effective_chat.id != config['owner_chat_id']:
        if update.message:
            update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return

    keyboard = [
        [InlineKeyboardButton("⏱️ Изменить время доступа", callback_data='change_duration')],
        [InlineKeyboardButton("🔗 Изменить URL панели", callback_data='change_url')],
        [InlineKeyboardButton("🚪 Изменить порт панели", callback_data='change_port')],
        [InlineKeyboardButton("↩️ Назад", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = """🔧 <b>Изменение настроек бота</b>

Выберите параметр, который хотите изменить:

⏱️ <b>Время доступа</b> - Как долго ссылка будет активна
🔗 <b>URL панели</b> - Адрес веб-интерфейса 3X-UI
🚪 <b>Порт панели</b> - Порт, через который открывается доступ

⚠️ <b>Внимание!</b> При изменении URL или порта старый порт будет автоматически закрыт."""

    if update.message:
        update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')
    elif update.callback_query:
        update.callback_query.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

def change_config_button_handler(update: Update, context: CallbackContext):
    """Обработка нажатий кнопок в меню /change_config"""
    global awaiting_input_for, change_config_initiator_chat_id
    
    if not update.callback_query:
        return

    query = update.callback_query
    query.answer()

    if update.effective_chat.id != config['owner_chat_id']:
        query.message.reply_text("❌ У вас нет доступа к этой функции.")
        return

    # Исправление: добавляем обработку нажатия кнопки "Настройки" (change_config)
    if query.data == 'change_config':
        # Показываем меню настроек
        change_config_command(update, context)
        # Сбрасываем состояние, если оно было установлено ранее
        awaiting_input_for = None
        change_config_initiator_chat_id = None
        return
        
    if query.data == 'change_duration':
        awaiting_input_for = 'access_duration_minutes'
        change_config_initiator_chat_id = update.effective_chat.id
        query.message.reply_text(f"Введите новое время доступа в минутах (текущее: {config['access_duration_minutes']} минут):")
        
    elif query.data == 'change_url':
        awaiting_input_for = 'panel_url'
        change_config_initiator_chat_id = update.effective_chat.id
        query.message.reply_text(f"Введите новый URL панели (текущий: {config['panel_url']}):")
        
    elif query.data == 'change_port':
        awaiting_input_for = 'panel_port'
        change_config_initiator_chat_id = update.effective_chat.id
        query.message.reply_text(f"Введите новый порт панели (текущий: {config['panel_port']}):")
        
    elif query.data == 'back_to_main':
        # Возвращаемся в главное меню
        start_command(update, context)
        # Сбрасываем состояние
        awaiting_input_for = None
        change_config_initiator_chat_id = None

def handle_text_input(update: Update, context: CallbackContext):
    """Обработка текстового ввода для /change_config"""
    global awaiting_input_for, change_config_initiator_chat_id, config
    
    # Проверяем, ожидаем ли мы ввод
    if awaiting_input_for is None or change_config_initiator_chat_id != update.effective_chat.id:
        # Если не ожидаем, просто игнорируем сообщение
        return

    user_input = update.message.text.strip()
    
    try:
        if awaiting_input_for == 'access_duration_minutes':
            is_valid, new_value, error_msg = validate_duration(user_input)
            if is_valid:
                if update_config_file('access_duration_minutes', new_value):
                    # Обновляем конфиг в памяти
                    config['access_duration_minutes'] = new_value
                    update.message.reply_text(f"✅ Время доступа успешно изменено на {new_value} минут.")
                else:
                    update.message.reply_text("❌ Ошибка при сохранении настроек.")
            else:
                update.message.reply_text(f"❌ {error_msg}")
                
        elif awaiting_input_for == 'panel_url':
            is_valid, extracted_port, error_msg = validate_url(user_input)
            if is_valid:
                old_port = config['panel_port']
                old_url = config['panel_url']
                
                # Обновляем URL
                if update_config_file('panel_url', user_input):
                    config['panel_url'] = user_input
                    
                    # Если порт изменился, обновляем его и закрываем старый
                    if extracted_port != old_port:
                        if apply_port_change(old_port, extracted_port):
                            if update_config_file('panel_port', extracted_port):
                                config['panel_port'] = extracted_port
                                update.message.reply_text(
                                    f"✅ URL панели успешно изменен с:\n<code>{old_url}</code>\nна:\n<code>{user_input}</code>\n\n"
                                    f"Порт изменен с {old_port} на {extracted_port}. Старый порт закрыт.",
                                    parse_mode='HTML'
                                )
                            else:
                                update.message.reply_text("❌ URL обновлен, но ошибка при сохранении нового порта в конфиге.")
                        else:
                            update.message.reply_text("❌ URL обновлен, но не удалось закрыть старый порт.")
                    else:
                        update.message.reply_text(
                            f"✅ URL панели успешно изменен с:\n<code>{old_url}</code>\nна:\n<code>{user_input}</code>",
                            parse_mode='HTML'
                        )
                else:
                    update.message.reply_text("❌ Ошибка при сохранении нового URL.")
            else:
                update.message.reply_text(f"❌ {error_msg}")
                
        elif awaiting_input_for == 'panel_port':
            is_valid, new_port, error_msg = validate_port(user_input)
            if is_valid:
                old_port = config['panel_port']
                
                # Закрываем старый порт
                if apply_port_change(old_port, new_port):
                    # Обновляем порт в конфиге
                    if update_config_file('panel_port', new_port):
                        config['panel_port'] = new_port
                        # Обновляем URL, если он содержит порт
                        old_url = config['panel_url']
                        try:
                            parsed = urlparse(old_url)
                            if ':' in parsed.netloc:
                                host = parsed.netloc.split(':')[0]
                                new_netloc = f"{host}:{new_port}"
                                new_url = old_url.replace(parsed.netloc, new_netloc)
                                if update_config_file('panel_url', new_url):
                                    config['panel_url'] = new_url
                                    update.message.reply_text(
                                        f"✅ Порт панели успешно изменен с {old_port} на {new_port}.\n"
                                        f"Старый порт закрыт.\n"
                                        f"URL обновлен с:\n<code>{old_url}</code>\nна:\n<code>{new_url}</code>",
                                        parse_mode='HTML'
                                    )
                                else:
                                    update.message.reply_text(
                                        f"✅ Порт панели успешно изменен с {old_port} на {new_port}.\n"
                                        f"Старый порт закрыт.\n"
                                        f"Ошибка при обновлении URL в конфиге."
                                    )
                            else:
                                update.message.reply_text(
                                    f"✅ Порт панели успешно изменен с {old_port} на {new_port}.\n"
                                    f"Старый порт закрыт."
                                )
                        except Exception as e:
                            update.message.reply_text(
                                f"✅ Порт панели успешно изменен с {old_port} на {new_port}.\n"
                                f"Старый порт закрыт.\n"
                                f"Предупреждение при обновлении URL: {e}"
                            )
                    else:
                        update.message.reply_text("❌ Ошибка при сохранении нового порта.")
                else:
                    update.message.reply_text("❌ Не удалось закрыть старый порт.")
            else:
                update.message.reply_text(f"❌ {error_msg}")
    except Exception as e:
        error_msg = f"❌ Неожиданная ошибка при обработке ввода: {e}"
        log_message(error_msg)
        update.message.reply_text(error_msg)
    finally:
        # Сбрасываем состояние ожидания ввода
        awaiting_input_for = None
        change_config_initiator_chat_id = None

# ==================== НОВЫЕ ФУНКЦИИ ДЛЯ SSH ====================

def open_ssh_command(update: Update, context: CallbackContext):
    """Обработка команды /open_ssh"""
    global ssh_timer, ssh_open_count
    
    if update.effective_chat.id != config['owner_chat_id']:
        update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return

    # Открываем SSH порт
    if open_ssh_port():
        ssh_open_count += 1
        total_minutes = ssh_open_count * 60  # 60 минут на каждый вызов
        
        # Отменяем предыдущий таймер, если он есть
        if ssh_timer and ssh_timer.is_alive():
            ssh_timer.cancel()
        
        # Запускаем новый таймер
        ssh_timer = threading.Timer(
            total_minutes * 60,  # Переводим минуты в секунды
            lambda: end_ssh_session(context.bot)
        )
        ssh_timer.start()
        
        update.message.reply_text(
            f"✅ SSH порт (22) открыт!\n"
            f"Будет автоматически закрыт через {total_minutes} минут ({ssh_open_count} час(-а/-ов)).\n"
            f"Повторный вызов /open_ssh увеличит время на 1 час."
        )
    else:
        update.message.reply_text("❌ Ошибка открытия SSH порта (22).")

def close_ssh_command(update: Update, context: CallbackContext):
    """Обработка команды /close_ssh"""
    global ssh_timer, ssh_open_count
    
    if update.effective_chat.id != config['owner_chat_id']:
        update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return

    # Отменяем таймер, если он есть
    if ssh_timer and ssh_timer.is_alive():
        ssh_timer.cancel()
    
    # Закрываем SSH порт
    if close_ssh_port():
        ssh_open_count = 0  # Сбрасываем счетчик
        update.message.reply_text("✅ SSH порт (22) закрыт.")
    else:
        update.message.reply_text("❌ Ошибка закрытия SSH порта (22).")

# ==================== КОНЕЦ НОВЫХ ФУНКЦИЙ ====================

def start_command(update: Update, context: CallbackContext):
    """Обработка команды /start"""
    if update.effective_chat.id != config['owner_chat_id']:
        if update.message:  # Проверяем, что message существует
            update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return

    keyboard = [
        [InlineKeyboardButton("🔓 Получить ссылку", callback_data='get_link')],
        [InlineKeyboardButton("🔒 Закрыть доступ", callback_data='close_link')],
        [InlineKeyboardButton("📊 Статус", callback_data='status')],
        [InlineKeyboardButton("⚙️ Настройки конфига", callback_data='change_config')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Получаем текущий статус
    server_status = "🟢 Онлайн" if check_server_status() else "🔴 Офлайн"
    xui_status = "🟢 Активен" if check_xui_status() else "🔴 Остановлен"

    message = f"""🤖 <b>Telegram Bot для управления 3X-UI</b>

<b>Доступные команды:</b>
/start - Главное меню
/help - Помощь
/status - Статус сервера
/getlink - Получить ссылку на панель
/offlink - Закрыть доступ к панели
/change_config - Изменить настройки
/open_ssh - Открыть SSH порт
/close_ssh - Закрыть SSH порт

<b>Статус системы:</b>
🖥️ Сервер: {server_status}
🎛️ 3X-UI: {xui_status}

Нажмите кнопки ниже для управления доступом к панели:"""

    update.message.reply_text(message, reply_markup=reply_markup, parse_mode='HTML')

def help_command(update: Update, context: CallbackContext):
    """Обработка команды /help"""
    if update.effective_chat.id != config['owner_chat_id']:
        if update.message:  # Проверяем, что message существует
            update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return

    message = """🤖 <b>Помощь по боту</b>

<b>Основные функции:</b>
• Мониторинг состояния сервера и 3X-UI
• Уведомления о SSH подключениях
• Контроль доступа к веб-панели

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
/status - Статус сервера и ресурсов
/getlink - Получить временную ссылку на панель
/offlink - Закрыть доступ к панели
/change_config - Изменить настройки бота
/open_ssh - Открыть SSH порт (22) на 1 час (накапливается)
/close_ssh - Закрыть SSH порт (22)

<b>Безопасность:</b>
Доступ к панели предоставляется на 30 минут и автоматически закрывается."""

    update.message.reply_text(message, parse_mode='HTML')

def status_command(update: Update, context: CallbackContext):
    """Обработка команды /status"""
    if update.effective_chat.id != config['owner_chat_id']:
        if update.message:
            update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return

    try:
        # 1. Имя хоста
        hostname = subprocess.run(['hostname'], capture_output=True, text=True, timeout=5).stdout.strip()
        
        # 2. Версия ОС
        os_info_result = subprocess.run(['lsb_release', '-d'], capture_output=True, text=True, timeout=5)
        os_version = os_info_result.stdout.split(":")[1].strip() if os_info_result.returncode == 0 else "Неизвестно"
        
        # 3. IP адрес
        ip_info_result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        ip_address = ip_info_result.stdout.strip().split()[0] if ip_info_result.returncode == 0 and ip_info_result.stdout.strip() else "Не удалось определить"
        
        # 4. Аптайм
        uptime_str = get_uptime_string()
        
        # 5. Загрузка CPU (мгновенная)
        cpu_percent = psutil.cpu_percent(interval=1) # 1-секундный интервал для актуальности
        
        # 6. Использование ОЗУ
        svmem = psutil.virtual_memory()
        ram_used = get_size(svmem.used)
        ram_total = get_size(svmem.total)
        ram_percent = svmem.percent
        
        # 7. Использование диска
        disk_usage = psutil.disk_usage('/')
        disk_used = get_size(disk_usage.used)
        disk_total = get_size(disk_usage.total)
        disk_percent = disk_usage.percent
        
        # 8. Load Average
        load_avg = os.getloadavg()
        load_avg_str = f"{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
        # Комментарии для Load Average (для 1 ядра)
        load_comment = ""
        if load_avg[0] > 1.0:
            load_comment = " (Высокая нагрузка!)"
        elif load_avg[0] > 0.7:
            load_comment = " (Повышенная нагрузка)"
        else:
            load_comment = " (Нормально)"

        # 9. Статус 3X-UI
        xui_status_result = subprocess.run(['systemctl', 'is-active', 'x-ui'], capture_output=True, text=True, timeout=10)
        xui_status = "🟢 Активен" if xui_status_result.stdout.strip() == 'active' else "🔴 Неактивен"

        message = f"""🖥️ <b>Статус сервера</b> (<code>{hostname}</code>)
🚀 <b>ОС:</b> {os_version}
🌐 <b>IPv4:</b> {ip_address}
⏱️ <b>Аптайм:</b> {uptime_str}
📈 <b>Загрузка CPU:</b> {cpu_percent}%
💾 <b>ОЗУ:</b> {ram_used} / {ram_total} ({ram_percent:.1f}%)
📂 <b>Диск (/):</b> {disk_used} / {disk_total} ({disk_percent:.1f}%)
📊 <b>Нагрузка (1/5/15 мин):</b> {load_avg_str}{load_comment}
🎛️ <b>3X-UI:</b> <code>{xui_status}</code>"""

        if update.message:
            update.message.reply_text(message, parse_mode='HTML')
        elif update.callback_query:
            update.callback_query.message.reply_text(message, parse_mode='HTML')
            
    except Exception as e:
        error_msg = f"❌ Ошибка получения статуса: {e}"
        log_message(error_msg)
        if update.message:
            update.message.reply_text(error_msg)
        elif update.callback_query:
            update.callback_query.message.reply_text(error_msg)

def get_link_command(update: Update, context: CallbackContext):
    """Обработка команды /getlink"""
    global active_session, session_timer

    # Проверяем, что это сообщение, а не callback
    message_obj = update.message if hasattr(update, 'message') and update.message else None
    if not message_obj and hasattr(update, 'callback_query') and update.callback_query:
        message_obj = update.callback_query.message

    if update.effective_chat.id != config['owner_chat_id']:
        if message_obj:
            message_obj.reply_text("❌ У вас нет доступа к этому боту.")
        return

    if active_session:
        if message_obj:
            message_obj.reply_text("⚠️ Сессия уже активна! Дождитесь завершения текущей сессии.")
        return

    # Открываем порт
    if open_panel_port(config['panel_port']):
        active_session = True
        # Запускаем таймер для автоматического закрытия
        session_timer = threading.Timer(
            config['access_duration_minutes'] * 60,
            lambda: end_session(context.bot)
        )
        session_timer.start()

        # Отправляем ссылку
        message_text = f"""✅ <b>Доступ к панели открыт!</b>

🔗 Ссылка: {config['panel_url']}

⏰ Доступ будет автоматически закрыт через {config['access_duration_minutes']} минут."""

        if message_obj:
            message_obj.reply_text(message_text, parse_mode='HTML')
    else:
        if message_obj:
            message_obj.reply_text("❌ Ошибка открытия доступа к панели.")

def off_link_command(update: Update, context: CallbackContext):
    """Обработка команды /offlink"""
    global active_session, session_timer

    # Проверяем, что это сообщение, а не callback
    message_obj = update.message if hasattr(update, 'message') and update.message else None
    if not message_obj and hasattr(update, 'callback_query') and update.callback_query:
        message_obj = update.callback_query.message

    if update.effective_chat.id != config['owner_chat_id']:
        if message_obj:
            message_obj.reply_text("❌ У вас нет доступа к этому боту.")
        return

    if not active_session:
        if message_obj:
            message_obj.reply_text("ℹ️ Порт уже закрыт. Нет активной сессии.")
        return

    # Отменяем таймер если он есть
    if session_timer and session_timer.is_alive():
        session_timer.cancel()

    # Закрываем порт
    if close_panel_port(config['panel_port']):
        active_session = False
        if message_obj:
            message_obj.reply_text("✅ Доступ к панели закрыт. Порт заблокирован.")
        log_message("Порт панели закрыт по команде пользователя")
    else:
        if message_obj:
            message_obj.reply_text("❌ Ошибка закрытия доступа к панели.")

def button_handler(update: Update, context: CallbackContext):
    """Обработка нажатий кнопок"""
    if not update.callback_query:
        return

    query = update.callback_query
    query.answer()

    if query.data == 'get_link':
        # Создаем фиктивный update для вызова get_link_command
        get_link_command(update, context)
    elif query.data == 'close_link':
        # Создаем фиктивный update для вызова off_link_command
        off_link_command(update, context)
    elif query.data == 'status':
        # Создаем фиктивный update для вызова status_command
        status_command(update, context)
    elif query.data in ['change_config', 'change_duration', 'change_url', 'change_port', 'back_to_main']:
        # Обрабатываем кнопки меню /change_config
        change_config_button_handler(update, context)

def main():
    """Основная функция бота"""
    try:
        # Создаем updater БЕЗ автоматической обработки сигналов
        updater = Updater(
            config['telegram_token'],
            use_context=True,
            workers=4
        )

        # Устанавливаем меню бота
        set_bot_commands(updater.bot)

        # Регистрация обработчиков команд
        updater.dispatcher.add_handler(CommandHandler("start", start_command))
        updater.dispatcher.add_handler(CommandHandler("help", help_command))
        updater.dispatcher.add_handler(CommandHandler("status", status_command))
        updater.dispatcher.add_handler(CommandHandler("getlink", get_link_command)) # <-- Исправлено на нижний регистр
        updater.dispatcher.add_handler(CommandHandler("offlink", off_link_command)) # <-- Исправлено на нижний регистр
        updater.dispatcher.add_handler(CommandHandler("change_config", change_config_command)) # <-- Новый обработчик
        updater.dispatcher.add_handler(CommandHandler("open_ssh", open_ssh_command)) # <-- Новый обработчик
        updater.dispatcher.add_handler(CommandHandler("close_ssh", close_ssh_command)) # <-- Новый обработчик
        
        # Регистрация обработчика callback кнопок
        updater.dispatcher.add_handler(CallbackQueryHandler(button_handler))
        
        # Регистрация обработчика текстовых сообщений (для /change_config)
        updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_input))

        log_message("Бот запущен")
        updater.start_polling()
        updater.idle()

    except Exception as e:
        log_message(f"Критическая ошибка бота: {e}")

if __name__ == '__main__':
    main()
