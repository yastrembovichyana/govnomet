#!/usr/bin/env python3
"""
Модуль для настройки логирования ГовноМёт
"""

import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime

class GovnometLogger:
    """Класс для настройки логирования игры ГовноМёт"""
    
    def __init__(self, log_dir: str = "logs", max_size_mb: int = 2):
        self.log_dir = Path(log_dir)
        self.max_size_bytes = max_size_mb * 1024 * 1024  # Конвертируем в байты
        self.setup_logging()
    
    def setup_logging(self):
        """Настройка системы логирования"""
        # Создаем директорию для логов если её нет
        self.log_dir.mkdir(exist_ok=True)
        
        # Основной логгер
        self.logger = logging.getLogger('govnomet')
        self.logger.setLevel(logging.INFO)
        
        # Очищаем существующие обработчики
        self.logger.handlers.clear()
        
        # Форматтер для логов
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Обработчик для консоли
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Обработчик для файла с ротацией
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_dir / "govnomet.log",
            maxBytes=self.max_size_bytes,
            backupCount=5,  # Храним 5 файлов бэкапа
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Обработчик для ошибок
        error_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_dir / "govnomet_errors.log",
            maxBytes=self.max_size_bytes,
            backupCount=3,  # Храним 3 файла бэкапа для ошибок
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        
        # Добавляем обработчики к логгеру
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        
        # Логгер для базы данных
        self.db_logger = logging.getLogger('govnomet.database')
        self.db_logger.setLevel(logging.INFO)
        
        # Логгер для игровой логики
        self.game_logger = logging.getLogger('govnomet.game')
        self.game_logger.setLevel(logging.INFO)
        
        # Логгер для бота
        self.bot_logger = logging.getLogger('govnomet.bot')
        self.bot_logger.setLevel(logging.INFO)
        
        # Логгер для планировщика рейтингов
        self.scheduler_logger = logging.getLogger('govnomet.scheduler')
        self.scheduler_logger.setLevel(logging.INFO)
    
    def get_logger(self, name: str = None) -> logging.Logger:
        """Получение логгера по имени"""
        if name:
            return logging.getLogger(f'govnomet.{name}')
        return self.logger
    
    def log_startup(self):
        """Логирование запуска приложения"""
        self.logger.info("🚀 ГовноМёт запускается...")
        self.logger.info(f"📁 Директория логов: {self.log_dir.absolute()}")
        self.logger.info(f"📏 Максимальный размер лога: {self.max_size_bytes // (1024*1024)} МБ")
        self.logger.info(f"🔄 Количество файлов бэкапа: 5")
        self.logger.info(f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    def log_shutdown(self):
        """Логирование завершения приложения"""
        self.logger.info("👋 ГовноМёт завершает работу")
        self.logger.info(f"⏰ Время завершения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    def error(self, message: str):
        """Логирование ошибки"""
        self.logger.error(message)
    
    def info(self, message: str):
        """Логирование информации"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """Логирование предупреждения"""
        self.logger.warning(message)
    
    def debug(self, message: str):
        """Логирование отладочной информации"""
        self.logger.debug(message)
    
    def cleanup_old_logs(self):
        """Очистка старых логов"""
        try:
            log_files = list(self.log_dir.glob("*.log*"))
            total_size = sum(f.stat().st_size for f in log_files)
            total_size_mb = total_size / (1024 * 1024)
            
            self.logger.info(f"🧹 Очистка логов: найдено {len(log_files)} файлов")
            self.logger.info(f"📊 Общий размер логов: {total_size_mb:.2f} МБ")
            
            # Удаляем файлы старше 30 дней
            import time
            current_time = time.time()
            thirty_days_ago = current_time - (30 * 24 * 60 * 60)
            
            deleted_count = 0
            for log_file in log_files:
                if log_file.stat().st_mtime < thirty_days_ago:
                    log_file.unlink()
                    deleted_count += 1
            
            if deleted_count > 0:
                self.logger.info(f"🗑️ Удалено {deleted_count} старых файлов логов")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при очистке логов: {e}")

# Глобальный экземпляр логгера
govnomet_logger = GovnometLogger()

def get_logger(name: str = None) -> logging.Logger:
    """Глобальная функция для получения логгера"""
    return govnomet_logger.get_logger(name)

def setup_logging(log_dir: str = "logs", max_size_mb: int = 2):
    """Глобальная функция для настройки логирования"""
    global govnomet_logger
    govnomet_logger = GovnometLogger(log_dir, max_size_mb)
    return govnomet_logger

# Пример использования
if __name__ == "__main__":
    # Настройка логирования
    logger = setup_logging("test_logs", 1)  # 1 МБ для тестов
    
    # Тестирование различных уровней логирования
    logger.log_startup()
    
    test_logger = get_logger("test")
    test_logger.info("ℹ️ Тестовое информационное сообщение")
    test_logger.warning("⚠️ Тестовое предупреждение")
    test_logger.error("❌ Тестовая ошибка")
    test_logger.debug("🔍 Тестовое отладочное сообщение")
    
    # Тестирование специализированных логгеров
    db_logger = get_logger("database")
    db_logger.info("🗄️ Тест логгера базы данных")
    
    game_logger = get_logger("game")
    game_logger.info("🎮 Тест логгера игровой логики")
    
    logger.log_shutdown()
    
    print("✅ Тест логирования завершен! Проверьте папку test_logs/")
