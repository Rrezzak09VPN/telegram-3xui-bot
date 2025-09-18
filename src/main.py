#!/usr/bin/env python3
import json
import threading
import time
import subprocess
import socket
from datetime import datetime

# Загрузка конфигурации
with open('config.json', 'r') as f:
    config = json.load(f)

def log_message(message):
    """Функция для логирования сообщений"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - MAIN - {message}"
    print(log_entry)
    with open(config['log_file'], 'a') as f:
        f.write(log_entry + '\n')

def check_port_status(port):
    """Проверка статуса порта в UFW"""
    try:
        result = subprocess.run(['ufw', 'status'], 
                              capture_output=True, text=True, check=True)
        # Ищем строку с портом
        for line in result.stdout.split('\n'):
            if f'{port}/tcp' in line and 'ALLOW' in line:
                return True
        return False
    except Exception as e:
        log_message(f"Ошибка проверки статуса порта {port}: {e}")
        return False

def close_panel_port(port):
    """Закрытие порта панели через UFW"""
    try:
        subprocess.run(['ufw', 'deny', str(port)], check=True, capture_output=True)
        log_message(f"Порт {port} закрыт")
        return True
    except Exception as e:
        log_message(f"Ошибка закрытия порта {port}: {e}")
        return False

def cleanup_on_start():
    """Очистка при запуске - закрываем открытые порты"""
    log_message("Выполняем очистку при запуске...")
    
    # Проверяем и закрываем порт панели если он открыт
    if check_port_status(config['panel_port']):
        log_message(f"Найден открытый порт {config['panel_port']} при запуске. Закрываем...")
        close_panel_port(config['panel_port'])

def health_check():
    """Проверка здоровья всех компонентов"""
    try:
        # Проверяем, что все потоки живы
        for thread in threading.enumerate():
            if not thread.is_alive() and thread != threading.main_thread():
                log_message(f"Поток {thread.name} не активен!")
        
        # Проверяем доступность локальных сервисов
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(('127.0.0.1', config['panel_port']))
        sock.close()
        
        log_message("Health check: OK")
        return True
    except Exception as e:
        log_message(f"Health check ошибка: {e}")
        return False

def start_bot():
    """Запуск Telegram бота"""
    try:
        log_message("Запуск Telegram бота...")
        import bot
        bot.main()
    except Exception as e:
        log_message(f"Ошибка запуска Telegram бота: {e}")

def start_system_monitor():
    """Запуск системного мониторинга"""
    try:
        log_message("Запуск системного мониторинга...")
        import monitor
        monitor.monitor_system()
    except Exception as e:
        log_message(f"Ошибка запуска системного мониторинга: {e}")

def start_ssh_monitor():
    """Запуск SSH мониторинга"""
    try:
        log_message("Запуск SSH мониторинга...")
        import ssh_monitor
        ssh_monitor.monitor_ssh_logs()
    except Exception as e:
        log_message(f"Ошибка запуска SSH мониторинга: {e}")

def main():
    """Главная функция запуска всех компонентов"""
    log_message("Запуск Telegram Bot для 3X-UI...")
    
    # Выполняем очистку при запуске
    cleanup_on_start()
    
    # Запускаем все компоненты в отдельных потоках
    threads = []
    
    # Telegram бот
    bot_thread = threading.Thread(target=start_bot, name="BotThread", daemon=True)
    bot_thread.start()
    threads.append(bot_thread)
    
    # Системный мониторинг
    monitor_thread = threading.Thread(target=start_system_monitor, name="MonitorThread", daemon=True)
    monitor_thread.start()
    threads.append(monitor_thread)
    
    # SSH мониторинг
    ssh_thread = threading.Thread(target=start_ssh_monitor, name="SSHThread", daemon=True)
    ssh_thread.start()
    threads.append(ssh_thread)
    
    log_message("Все компоненты запущены")
    
    # Основной цикл health-check
    try:
        while True:
            time.sleep(300)  # Каждые 5 минут
            health_check()
            log_message("Главный процесс активен...")
    except KeyboardInterrupt:
        log_message("Завершение работы по Ctrl+C...")
        exit(0)

if __name__ == '__main__':
    main()
