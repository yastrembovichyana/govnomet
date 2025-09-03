import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, GAME_SETTINGS, LOGGING_SETTINGS
from database import Database
from game_logic import GameLogic
from logger_config import setup_logging, get_logger

# Настройка логирования
logger = setup_logging(
    log_dir=LOGGING_SETTINGS['log_directory'],
    max_size_mb=LOGGING_SETTINGS['max_log_size_mb']
)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация компонентов
db = Database()
game_logic = GameLogic()

# Кэш участников чатов (в реальности лучше получать через Telegram API)
chat_participants_cache = {}

def get_throw_button() -> InlineKeyboardMarkup:
    """Создание кнопки для броска говна"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💩 Кинуть говно", callback_data="throw_shit"))
    return builder.as_markup()

async def get_chat_participants(chat_id: int) -> List[Tuple[int, str]]:
    """Получение участников чата"""
    try:
        # В реальности здесь нужно использовать Telegram API для получения участников
        # Пока используем кэш и базу данных
        if chat_id not in chat_participants_cache:
            participants = await db.get_chat_participants(chat_id)
            chat_participants_cache[chat_id] = participants
        
        # Если участников нет, создаем заглушку
        if not chat_participants_cache[chat_id]:
            # Создаем тестовых участников для демонстрации
            test_participants = [
                (123456789, "test_user1"),
                (987654321, "test_user2"),
                (555666777, "test_user3")
            ]
            chat_participants_cache[chat_id] = test_participants
            logger.info(f"👥 Созданы тестовые участники для чата {chat_id}: {len(test_participants)}")
        
        return chat_participants_cache[chat_id]
    
    except Exception as e:
        logger.error(f"❌ Ошибка получения участников чата {chat_id}: {e}")
        return []

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"🚀 Команда /start от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    await message.answer(
        "🎯 Добро пожаловать в игру «ГовноМёт»!\n\n"
        "💩 Просто нажми кнопку ниже, чтобы кинуть говно в случайного участника чата.\n\n"
        "🎲 Результат всегда случайный - можешь попасть в цель, промахнуться или устроить говнобум!\n\n"
        "🔥 Цель игры - превратить чат в говнохаос!",
        reply_markup=get_throw_button()
    )
    
    logger.info(f"✅ Приветственное сообщение отправлено пользователю {user.username}")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"❓ Команда /help от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    help_text = (
        "🎯 <b>ГовноМёт - правила игры:</b>\n\n"
        "💩 <b>Как играть:</b>\n"
        "• Нажми кнопку «💩 Кинуть говно»\n"
        "• Бот случайно выберет цель\n"
        "• Результат будет показан в чате\n\n"
        "🎲 <b>Возможные исходы:</b>\n"
        "• 🎯 <b>Прямое попадание (40%)</b> - говно летит точно в цель\n"
        "• 🤡 <b>Промах (20%)</b> - говно попадает в метателя\n"
        "• 🤮 <b>Разлетелось (30%)</b> - говно задевает несколько участников\n"
        "• ⚡ <b>Особые эффекты (10%)</b> - бумеранг, лавина, кирпич и т.д.\n\n"
        "📊 <b>Команды:</b>\n"
        "/start - начать игру\n"
        "/help - показать эту справку\n"
        "/stats - показать статистику\n"
        "/ratings - показать рейтинги\n\n"
        "🔥 <b>Цель:</b> Устроить максимальный говнохаос в чате!"
    )
    
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Справка отправлена пользователю {user.username}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Показать статистику пользователя"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"📊 Команда /stats от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    user_id = user.id
    stats = await db.get_user_stats(user_id)
    
    if stats:
        stats_text = (
            f"📊 <b>Статистика @{message.from_user.username or 'user'}:</b>\n\n"
            f"🎯 <b>Прямых попаданий:</b> {stats['direct_hits']}\n"
            f"🤡 <b>Промахов:</b> {stats['misses']}\n"
            f"💩 <b>Сам себя обосрал:</b> {stats['self_hits']}\n"
            f"😵 <b>Страдал от других:</b> {stats['times_hit']}\n\n"
            f"🔥 <b>Общий счёт:</b> {stats['direct_hits'] - stats['misses'] - stats['self_hits']}"
        )
        logger.debug(f"📊 Статистика пользователя {user.username}: {stats}")
    else:
        stats_text = "📊 У вас пока нет статистики. Начните играть!"
        logger.info(f"📊 Пользователь {user.username} запросил статистику, но данных нет")
    
    await message.answer(stats_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Статистика отправлена пользователю {user.username}")

@dp.message(Command("ratings"))
async def cmd_ratings(message: types.Message):
    """Показать рейтинги"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"🏆 Команда /ratings от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    ratings = await db.get_ratings(chat_id, days=7)
    
    ratings_text = "🏆 <b>Рейтинги недели:</b>\n\n"
    
    if ratings.get('king'):
        username, hits = ratings['king']
        ratings_text += f"👑 <b>Король говна:</b> @{username} ({hits} попаданий)\n"
    
    if ratings.get('victim'):
        username, hit_count = ratings['victim']
        ratings_text += f"😵 <b>Главный обосранный:</b> @{username} ({hit_count} раз)\n"
    
    if ratings.get('idiot'):
        username, self_hits = ratings['idiot']
        ratings_text += f"🤡 <b>Долбоёб недели:</b> @{username} ({self_hits} раз)\n"
    
    if not any(ratings.values()):
        ratings_text += "📊 Пока нет данных для рейтингов. Играйте больше!"
    
    await message.answer(ratings_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Рейтинги отправлены пользователю {user.username}")

@dp.callback_query(F.data == "throw_shit")
async def process_throw_shit(callback: types.CallbackQuery):
    """Обработка нажатия кнопки броска говна"""
    try:
        # Проверяем, не устарел ли callback
        if callback.message.date and (datetime.now().replace(tzinfo=None) - callback.message.date.replace(tzinfo=None)).total_seconds() > 60:
            logger.warning(f"⚠️ Получен устаревший callback от {callback.from_user.username}")
            try:
                await callback.answer("⚠️ Кнопка устарела, попробуйте снова")
            except Exception:
                pass
            return
        
        user = callback.from_user
        chat_id = callback.message.chat.id
        
        logger.info(f"💩 Кнопка броска нажата пользователем {user.username} (ID: {user.id}) в чате {chat_id}")
        
        # Добавляем пользователя в базу
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Получаем участников чата
        participants = await get_chat_participants(chat_id)
        
        if not participants:
            logger.warning(f"⚠️ Не удалось получить участников чата {chat_id}")
            try:
                await callback.answer("❌ Не удалось получить участников чата")
            except Exception:
                logger.warning("⚠️ Не удалось ответить на callback (возможно, устарел)")
            return
        
        # Обрабатываем бросок
        game_result = game_logic.process_throw(
            initiator_id=user.id,
            initiator_username=user.username or f"user{user.id}",
            participants=participants,
            chat_id=chat_id
        )
        
        # Добавляем событие в базу
        for target in game_result['targets']:
            await db.add_event(
                initiator_id=user.id,
                target_id=target[0],
                outcome=game_result['outcome'],
                chat_id=chat_id
            )
        
        # Обновляем статистику
        await db.update_user_stats(user.id, game_result['outcome'], is_target=False)
        for target in game_result['targets']:
            await db.update_user_stats(target[0], game_result['outcome'], is_target=True)
        
        # Формируем сообщение с результатом
        emoji = game_logic.get_emoji_for_outcome(game_result['outcome'])
        result_message = f"{emoji} {game_result['message']}"
        
        # Отправляем результат
        await callback.message.answer(
            result_message,
            reply_markup=get_throw_button()
        )
        
        # Отвечаем на callback
        try:
            await callback.answer("💩 Говно полетело!")
        except Exception:
            logger.warning("⚠️ Не удалось ответить на callback (возможно, устарел)")
        
        logger.info(f"✅ Бросок завершен: {user.username} -> {game_result['outcome']} -> {len(game_result['targets'])} целей")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки броска: {e}")
        try:
            await callback.answer("❌ Что-то пошло не так")
        except Exception:
            logger.warning("⚠️ Не удалось ответить на callback (возможно, устарел)")

@dp.message(F.text.contains("кинуть говно в"))
async def handle_manual_throw(message: types.Message):
    """Обработка ручного ввода команды броска"""
    try:
        user = message.from_user
        chat_id = message.chat.id
        
        logger.info(f"💩 Ручной ввод команды от {user.username} (ID: {user.id}) в чате {chat_id}: {message.text}")
        
        # Извлекаем username цели
        text = message.text.lower()
        if "кинуть говно в @" in text:
            target_username = text.split("кинуть говно в @")[1].split()[0]
            logger.debug(f"🎯 Цель ручного броска: @{target_username}")
            
            # Удаляем сообщение через 3 секунды
            await asyncio.sleep(GAME_SETTINGS['message_delete_delay'])
            try:
                await message.delete()
                logger.debug(f"🗑️ Сообщение пользователя {user.username} удалено")
            except:
                logger.warning(f"⚠️ Не удалось удалить сообщение пользователя {user.username}")
                pass  # Игнорируем ошибки удаления
            
            # Добавляем пользователя в базу
            await db.add_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            # Получаем участников чата
            participants = await get_chat_participants(chat_id)
            
            if participants:
                # Обрабатываем бросок
                game_result = game_logic.process_throw(
                    initiator_id=user.id,
                    initiator_username=user.username or f"user{user.id}",
                    participants=participants,
                    chat_id=chat_id
                )
                
                # Добавляем событие в базу
                for target in game_result['targets']:
                    await db.add_event(
                        initiator_id=user.id,
                        target_id=target[0],
                        outcome=game_result['outcome'],
                        chat_id=chat_id
                    )
                
                # Обновляем статистику
                await db.update_user_stats(user.id, game_result['outcome'], is_target=False)
                for target in game_result['targets']:
                    await db.update_user_stats(target[0], game_result['outcome'], is_target=True)
                
                # Формируем сообщение с результатом
                emoji = game_logic.get_emoji_for_outcome(game_result['outcome'])
                result_message = f"{emoji} {game_result['message']}"
                
                # Отправляем результат
                await message.answer(
                    result_message,
                    reply_markup=get_throw_button()
                )
                
                logger.info(f"✅ Ручной бросок завершен: {user.username} -> {game_result['outcome']} -> {len(game_result['targets'])} целей")
            else:
                logger.warning(f"⚠️ Не удалось получить участников чата {chat_id} для ручного броска")
                await message.answer("❌ Не удалось получить участников чата для броска")
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки ручного броска: {e}")

async def main():
    """Главная функция"""
    logger.log_startup()
    
    max_retries = 5
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            # Запускаем бота
            logger.info(f"🤖 Бот ГовноМёт запущен и готов к работе! (попытка {attempt + 1}/{max_retries})")
            await dp.start_polling(bot, skip_updates=True)
            break  # Если успешно, выходим из цикла
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска бота (попытка {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"🔄 Повторная попытка через {retry_delay} секунд...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Увеличиваем задержку с каждой попыткой
            else:
                logger.error("❌ Все попытки запуска исчерпаны. Бот не может быть запущен.")
                break
    
    finally:
        logger.log_shutdown()
        try:
            await bot.session.close()
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при закрытии сессии: {e}")

if __name__ == "__main__":
    asyncio.run(main())

