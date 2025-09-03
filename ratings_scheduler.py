#!/usr/bin/env python3
"""
Модуль для автоматического обновления рейтингов в игре ГовноМёт
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from database import Database
from config import GAME_SETTINGS
from logger_config import get_logger

logger = get_logger('scheduler')

class RatingsScheduler:
    def __init__(self, database: Database):
        self.db = database
        self.active_chats = set()
        self.is_running = False
        logger.info("📊 Планировщик рейтингов ГовноМёт инициализирован")
    
    async def start_scheduler(self):
        """Запуск планировщика рейтингов"""
        if self.is_running:
            logger.warning("⚠️ Планировщик уже запущен")
            return
        
        self.is_running = True
        logger.info("🚀 Запуск планировщика рейтингов")
        
        try:
            while self.is_running:
                await self.update_all_ratings()
                await asyncio.sleep(GAME_SETTINGS['ratings_update_interval'])
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике рейтингов: {e}")
        finally:
            self.is_running = False
    
    async def stop_scheduler(self):
        """Остановка планировщика"""
        self.is_running = False
        logger.info("🛑 Планировщик рейтингов остановлен")
    
    async def update_all_ratings(self):
        """Обновление рейтингов для всех активных чатов"""
        try:
            # Получаем список активных чатов
            active_chats = await self.get_active_chats()
            
            logger.info(f"🔄 Обновление рейтингов для {len(active_chats)} активных чатов")
            
            for chat_id in active_chats:
                await self.update_chat_ratings(chat_id)
            
            logger.info(f"✅ Обновлены рейтинги для {len(active_chats)} чатов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления рейтингов: {e}")
    
    async def get_active_chats(self) -> List[int]:
        """Получение списка активных чатов"""
        try:
            # В реальности здесь нужно получать список чатов через Telegram API
            # Пока возвращаем тестовые данные
            test_chats = [1, 2, 3]  # Тестовые ID чатов
            logger.debug(f"📋 Получено {len(test_chats)} активных чатов")
            return test_chats
        except Exception as e:
            logger.error(f"❌ Ошибка получения активных чатов: {e}")
            return []
    
    async def update_chat_ratings(self, chat_id: int):
        """Обновление рейтингов для конкретного чата"""
        try:
            logger.debug(f"📊 Обновление рейтингов для чата {chat_id}")
            
            # Получаем рейтинги за неделю
            weekly_ratings = await self.db.get_ratings(chat_id, days=7)
            
            # Получаем рейтинги за день
            daily_ratings = await self.db.get_ratings(chat_id, days=1)
            
            # Здесь можно добавить логику отправки рейтингов в чат
            # Например, отправлять топ-3 рейтинга каждые 24 часа
            
            logger.info(f"✅ Рейтинги для чата {chat_id} обновлены")
            logger.debug(f"📈 Еженедельные рейтинги: {weekly_ratings}")
            logger.debug(f"📅 Ежедневные рейтинги: {daily_ratings}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления рейтингов для чата {chat_id}: {e}")
    
    async def get_formatted_ratings(self, chat_id: int, days: int = 7) -> str:
        """Получение отформатированных рейтингов для отправки в чат"""
        try:
            ratings = await self.db.get_ratings(chat_id, days)
            
            if days == 1:
                period = "дня"
            elif days == 7:
                period = "недели"
            else:
                period = f"{days} дней"
            
            text = f"🏆 <b>Рейтинги за {period}:</b>\n\n"
            
            if ratings.get('king'):
                username, hits = ratings['king']
                text += f"👑 <b>Король говна:</b> @{username} ({hits} попаданий)\n"
            
            if ratings.get('victim'):
                username, hit_count = ratings['victim']
                text += f"😵 <b>Главный обосранный:</b> @{username} ({hit_count} раз)\n"
            
            if ratings.get('idiot'):
                username, self_hits = ratings['idiot']
                text += f"🤡 <b>Долбоёб {period}:</b> @{username} ({self_hits} раз)\n"
            
            if not any(ratings.values()):
                text += "📊 Пока нет данных для рейтингов. Играйте больше!"
            
            logger.debug(f"📝 Сформированы рейтинги для чата {chat_id} за {period}")
            return text
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования рейтингов для чата {chat_id}: {e}")
            return "❌ Ошибка получения рейтингов"
    
    async def add_chat_to_scheduler(self, chat_id: int):
        """Добавление чата в планировщик рейтингов"""
        self.active_chats.add(chat_id)
        logger.info(f"➕ Чат {chat_id} добавлен в планировщик рейтингов")
    
    async def remove_chat_from_scheduler(self, chat_id: int):
        """Удаление чата из планировщика рейтингов"""
        self.active_chats.discard(chat_id)
        logger.info(f"➖ Чат {chat_id} удален из планировщика рейтингов")
    
    async def get_scheduler_status(self) -> Dict:
        """Получение статуса планировщика"""
        status = {
            'is_running': self.is_running,
            'active_chats_count': len(self.active_chats),
            'active_chats': list(self.active_chats),
            'last_update': datetime.now().isoformat()
        }
        logger.debug(f"📊 Статус планировщика: {status}")
        return status

# Пример использования
async def main():
    """Пример использования планировщика рейтингов"""
    logger.info("🧪 Тестирование планировщика рейтингов")
    
    db = Database()
    scheduler = RatingsScheduler(db)
    
    # Добавляем тестовые чаты
    await scheduler.add_chat_to_scheduler(1)
    await scheduler.add_chat_to_scheduler(2)
    
    # Получаем статус
    status = await scheduler.get_scheduler_status()
    logger.info(f"📊 Статус планировщика: {status}")
    
    # Запускаем планировщик (кратковременно для теста)
    logger.info("🚀 Запуск планировщика для тестирования")
    await scheduler.start_scheduler()

if __name__ == "__main__":
    asyncio.run(main())
