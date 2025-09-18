#!/usr/bin/env python3
import json
import subprocess
import time
import requests
import threading
import urllib3
import psutil
import os
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime
from telegram import Bot

# Загрузка конфигурации
with open('config.json', 'r') as f:
    config = json.load(f)

# Глобальные переменные состояния
previous_server_status = None  # None = неизвестно
previous_xui_status = None     # None = неизвестно

# Путь к файлу состояния
STATE_FILE = '/var/lib/telegram-bot/state.json'

def log_message(message):
    """Функция для логирования сообщений"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - SYSTEM_MONITOR - {message}"
    print(log_entry)
    with open(config['log_file'], 'a') as f:
        f.write(log_entry + '\n')

def load_state():
    """Загрузка состояния из файла"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        else:
            # Создаем начальный файл состояния
            initial_state = {
                "last_status": {"server": True, "xui": True},
                "last_check": "2025-01-01 00:00:00",
                "last_uptime": 0
            }
            save_state(initial_state)
            return initial_state
    except Exception as e:
        log_message(f"Ошибка загрузки состояния: {e}")
        return {
            "last_status": {"server": True, "xui": True},
            "last_check": "2025-01-01 00:00:00",
            "last_uptime": 0
        }

def save_state(state):
    """Сохранение состояния в файл"""
    try:
        # Создаем каталог если его нет
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        log_message(f"Состояние сохранено: {STATE_FILE}")
    except Exception as e:
        log_message(f"Ошибка сохранения состояния: {e}")

def get_system_uptime():
    """Получение uptime системы в секундах"""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        return uptime_seconds
    except:
        return 0

def send_telegram_message(message):
    """Отправка сообщения в Telegram владельцу"""
    try:
        bot = Bot(token=config['telegram_token'])
        bot.send_message(chat_id=config['owner_chat_id'], text=message, parse_mode='HTML')
        return True
    except Exception as e:
        log_message(f"Ошибка отправки Telegram сообщения: {e}")
        return False

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

def check_initial_status():
    """Проверка начального состояния при запуске"""
    global previous_server_status, previous_xui_status
    
    log_message("Проверка начального состояния системы...")
    
    # Загружаем предыдущее состояние
    state = load_state()
    log_message(f"Загружено состояние: {state}")
    
    # Получаем текущий uptime
    current_uptime = get_system_uptime()
    last_uptime = state.get("last_uptime", 0)
    
    log_message(f"Текущий uptime: {current_uptime}, последний uptime: {last_uptime}")
    
    # Проверяем, была ли перезагрузка (текущий uptime меньше последнего и последний был большой)
    if current_uptime < last_uptime and last_uptime > 300:  # Больше 5 минут
        message = "🔄 <b>Сервер перезагружен</b>\nСистема успешно восстановлена после перезагрузки!"
        send_telegram_message(message)
        log_message("Обнаружена перезагрузка по uptime")
    
    # Проверяем сервер
    current_server_status = check_server_status()
    previous_server_status = current_server_status
    
    # Проверяем x-ui
    current_xui_status = check_xui_status()
    previous_xui_status = current_xui_status
    
    # Отправляем начальный статус
    server_status_text = "🟢 Онлайн" if current_server_status else "🔴 Офлайн"
    xui_status_text = "🟢 Активен" if current_xui_status else "🔴 Остановлен"
    
    message = f"""🔄 <b>Мониторинг запущен</b>

<b>Текущий статус:</b>
🖥️ Сервер: {server_status_text}
🎛️ 3X-UI: {xui_status_text}"""
    
    send_telegram_message(message)
    log_message(f"Начальный статус: Сервер={server_status_text}, X-UI={xui_status_text}")

def monitor_system():
    """Основной цикл мониторинга системы"""
    global previous_server_status, previous_xui_status
    
    log_message("Системный мониторинг запущен")
    
    # Проверяем начальное состояние
    check_initial_status()
    
    while True:
        try:
            # Проверяем статус сервера
            current_server_status = check_server_status()
            if previous_server_status is not None and current_server_status != previous_server_status:
                if current_server_status:
                    message = "✅ <b>Сервер восстановлен</b>\nСервер снова доступен!"
                    send_telegram_message(message)
                    log_message("Сервер восстановлен")
                else:
                    message = "❌ <b>Сервер недоступен</b>\nПотеряна связь с сервером!"
                    send_telegram_message(message)
                    log_message("Сервер недоступен")
            previous_server_status = current_server_status
            
            # Проверяем статус x-ui
            current_xui_status = check_xui_status()
            if previous_xui_status is not None and current_xui_status != previous_xui_status:
                if current_xui_status:
                    message = "✅ <b>3X-UI восстановлен</b>\nСервис 3X-UI снова активен!"
                    send_telegram_message(message)
                    log_message("3X-UI восстановлен")
                else:
                    message = "❌ <b>3X-UI упал</b>\nСервис 3X-UI остановлен!"
                    send_telegram_message(message)
                    log_message("3X-UI упал")
            previous_xui_status = current_xui_status
            
            # Сохраняем текущее состояние с uptime
            state = {
                "last_status": {
                    "server": current_server_status,
                    "xui": current_xui_status
                },
                "last_check": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "last_uptime": get_system_uptime()
            }
            save_state(state)
            
            # Ждем до следующей проверки
            time.sleep(config['check_interval_seconds'])
            
        except Exception as e:
            log_message(f"Ошибка системного мониторинга: {e}")
            time.sleep(30)

if __name__ == '__main__':
    monitor_system()
