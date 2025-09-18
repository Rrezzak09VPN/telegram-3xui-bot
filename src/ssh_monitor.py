#!/usr/bin/env python3

import json
import subprocess
import time
import re
import urllib3
import requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime
from telegram import Bot

# Загрузка конфигурации
with open('config.json', 'r') as f:
    config = json.load(f)

def log_message(message):
    """Функция для логирования сообщений"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - SSH_MONITOR - {message}"
    print(log_entry)
    
    # Также записываем в общий лог-файл бота
    try:
        with open(config['log_file'], 'a') as log_file:
            log_file.write(log_entry + '\n')
    except Exception as e:
        pass # Игнорируем ошибки записи в лог

def send_telegram_message(message):
    """Функция отправки сообщения через Telegram бот"""
    try:
        bot = Bot(token=config['telegram_token'])
        bot.send_message(chat_id=config['owner_chat_id'], text=message, parse_mode='HTML')
        return True
    except Exception as e:
        log_message(f"Ошибка отправки Telegram сообщения: {e}")
        return False

def get_geo_info(ip):
    """Получение геоинформации по IP через ip-api.com"""
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            country = data.get('country', 'N/A')
            region = data.get('regionName', 'N/A')
            city = data.get('city', 'N/A')
            isp = data.get('isp', 'N/A')
            geo_info = f"Страна: {country}, Регион: {region}, Город: {city}, ISP: {isp}"
            return geo_info
        else:
            message = data.get('message', 'Неизвестная ошибка API')
            log_message(f"API ip-api.com вернул ошибку для IP {ip}: {message}")
            return f"Геоинформация недоступна ({message})"
            
    except requests.exceptions.Timeout:
        log_message(f"Таймаут при запросе геоинформации для IP {ip}")
        return "Геоинформация недоступна (таймаут)"
    except requests.exceptions.RequestException as e:
        log_message(f"Ошибка сети при запросе геоинформации для IP {ip}: {e}")
        return "Геоинформация недоступна (ошибка сети)"
    except json.JSONDecodeError:
        log_message(f"Ошибка декодирования JSON от API для IP {ip}")
        return "Геоинформация недоступна (ошибка данных)"
    except Exception as e:
        log_message(f"Неожиданная ошибка при получении геоинформации для IP {ip}: {e}")
        return "Геоинформация недоступна"

def parse_ssh_log_line(line):
    """Парсинг строки SSH лога с поддержкой двух форматов времени"""
    
    # Регулярные выражения для разных форматов времени и типов записей
    
    # Новый формат времени (ISO 8601) - Accepted
    accepted_pattern_new = r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.\d+\+\d{2}:\d{2}.*sshd.*Accepted (?P<auth_type>\w+) for (?P<user>\w+) from (?P<ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+)'
    
    # Новый формат времени (ISO 8601) - Failed
    failed_pattern_new = r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.\d+\+\d{2}:\d{2}.*sshd.*Failed (?P<auth_type>\w+) for (?P<user>\w+) from (?P<ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+)'
    
    # Новый формат времени (ISO 8601) - Invalid user
    invalid_user_pattern_new = r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.\d+\+\d{2}:\d{2}.*sshd.*Invalid user (?P<user>\w+) from (?P<ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+)'
    
    # Старый формат времени (MMM DD HH:MM:SS) - Accepted
    accepted_pattern_old = r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}).*sshd.*Accepted (?P<auth_type>\w+) for (?P<user>\w+) from (?P<ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+)'
    
    # Старый формат времени (MMM DD HH:MM:SS) - Failed
    failed_pattern_old = r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}).*sshd.*Failed (?P<auth_type>\w+) for (?P<user>\w+) from (?P<ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+)'
    
    # Старый формат времени (MMM DD HH:MM:SS) - Invalid user
    invalid_user_pattern_old = r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}).*sshd.*Invalid user (?P<user>\w+) from (?P<ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+)'

    # Проверяем все паттерны по очереди
    for pattern, type_str in [
        (accepted_pattern_new, 'success'), 
        (failed_pattern_new, 'failed'), 
        (invalid_user_pattern_new, 'failed'),
        (accepted_pattern_old, 'success'), 
        (failed_pattern_old, 'failed'), 
        (invalid_user_pattern_old, 'failed')
    ]:
        match = re.search(pattern, line)
        if match:
            data = match.groupdict()
            
            # Преобразуем timestamp в единый формат
            try:
                if 'T' in data['timestamp']:
                    # Новый формат: 2025-09-17T10:22:45 -> 2025-09-17 10:22:45
                    dt_obj = datetime.fromisoformat(data['timestamp'])
                    formatted_timestamp = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    # Старый формат: Sep 17 10:10:38 -> 2025-09-17 10:10:38
                    current_year = datetime.now().year
                    full_timestamp_str = f"{current_year} {data['timestamp']}"
                    dt_obj = datetime.strptime(full_timestamp_str, '%Y %b %d %H:%M:%S')
                    formatted_timestamp = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
                
                data['timestamp'] = formatted_timestamp
            except Exception as e:
                log_message(f"Ошибка преобразования времени: {e}. Оставляем как есть.")
                
            data['type'] = type_str
            return data
            
    return None

def monitor_ssh_logs():
    """Основной цикл мониторинга SSH логов"""
    log_message("SSH мониторинг запущен")
    
    # Получаем текущую позицию в логе
    try:
        with open(config['ssh_log_file'], 'r') as f:
            f.seek(0, 2)  # Переходим в конец файла
            last_position = f.tell()
    except Exception as e:
        log_message(f"Ошибка открытия SSH лога: {e}")
        return

    while True:
        try:
            with open(config['ssh_log_file'], 'r') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()

            for line in new_lines:
                parsed = parse_ssh_log_line(line.strip())
                if parsed:
                    if parsed['type'] == 'success':
                        # Отправляем уведомление о успешной авторизации
                        message = f"""🔐 <b>SSH авторизация</b>

<b>Время:</b> {parsed['timestamp']}
<b>Пользователь:</b> {parsed['user']}
<b>IP адрес:</b> {parsed['ip']}
<b>Порт:</b> {parsed['port']} (порт сервера)
<b>Тип авторизации:</b> {parsed['auth_type']}
<b>Геоинформация:</b> {get_geo_info(parsed['ip'])}"""
                        
                        send_telegram_message(message)
                        log_message(f"SSH авторизация: {parsed['user']} с {parsed['ip']}")

                    elif parsed['type'] == 'failed':
                        # Логируем неудачные попытки
                        log_message(f"SSH неудачная попытка: {parsed['user']} с {parsed['ip']}")

            time.sleep(1)  # Проверяем каждую секунду

        except Exception as e:
            log_message(f"Ошибка мониторинга SSH: {e}")
            time.sleep(5)

if __name__ == '__main__':
    monitor_ssh_logs()
