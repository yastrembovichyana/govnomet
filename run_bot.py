#!/usr/bin/env python3
"""
Скрипт для запуска бота ГовноМёт
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Добавляем текущую директорию в путь для импортов
sys.path.append(str(Path(__file__).parent))

try:
    from bot import main
    from config import BOT_TOKEN, LOGGING_SETTINGS
    from logger_config import setup_logging, get_logger
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что все файлы находятся в одной директории")
    sys.exit(1)

def check_environment():
    """Проверка окружения"""
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("❌ Ошибка: токен бота не настроен!")
        print("1. Скопируйте env_example.txt в .env")
        print("2. Укажите ваш токен бота в файле .env")
        print("3. Получите токен у @BotFather в Telegram")
        return False
    
    return True

def check_dependencies():
    """Проверка зависимостей"""
    try:
        import aiogram
        import dotenv
        print("✅ Зависимости проверены")
        return True
    except ImportError as e:
        print(f"❌ Ошибка зависимостей: {e}")
        print("Установите зависимости: pip install -r requirements.txt")
        return False

async def run_bot():
    """Запуск бота"""
    try:
        # Настраиваем логирование
        logger = setup_logging(
            log_dir=LOGGING_SETTINGS['log_directory'],
            max_size_mb=LOGGING_SETTINGS['max_log_size_mb']
        )
        
        print("🚀 Запуск бота ГовноМёт...")
        print("📱 Бот готов к работе!")
        print("💡 Используйте /start в Telegram для начала игры")
        print("🛑 Для остановки нажмите Ctrl+C")
        print(f"📁 Логи сохраняются в папку: {LOGGING_SETTINGS['log_directory']}")
        print(f"📏 Максимальный размер лога: {LOGGING_SETTINGS['max_log_size_mb']} МБ")
        print("-" * 50)
        
        await main()
        
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        logger = get_logger()
        if hasattr(logger, 'log_shutdown'):
            logger.log_shutdown()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger = get_logger()
        logger.error(f"❌ Критическая ошибка запуска: {e}")
    finally:
        print("👋 Бот завершил работу")

def main_sync():
    """Синхронная обертка для запуска"""
    if not check_environment():
        return
    
    if not check_dependencies():
        return
    
    try:
        asyncio.run(run_bot())
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")

if __name__ == "__main__":
    main_sync()
