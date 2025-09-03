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
    builder.add(InlineKeyboardButton(text="💩 Метнуть говна", callback_data="throw_shit"))
    return builder.as_markup()

async def get_chat_participants(chat_id: int) -> List[Tuple[int, str]]:
    """Получение участников чата через Telegram API"""
    try:
        # Используем кэш для оптимизации (обновляем каждые 5 минут)
        cache_key = f"{chat_id}_{datetime.now().strftime('%Y%m%d_%H%M')[:-1]}"  # Округляем до 10 минут
        
        if cache_key not in chat_participants_cache:
            try:
                # Получаем реальных участников чата через Telegram API
                chat_member_count = await bot.get_chat_member_count(chat_id)
                logger.info(f"👥 В чате {chat_id} всего участников: {chat_member_count}")
                
                # Получаем список участников (максимум 200 для оптимизации)
                participants = []
                async for member in bot.get_chat_members(chat_id, limit=200):
                    if not member.user.is_bot:  # Исключаем ботов
                        username = member.user.username or member.user.first_name or f"user{member.user.id}"
                        participants.append((member.user.id, username))
                
                chat_participants_cache[cache_key] = participants
                logger.info(f"✅ Получено {len(participants)} участников чата {chat_id} через API")
                
            except Exception as api_error:
                logger.warning(f"⚠️ Не удалось получить участников через API: {api_error}")
                # Fallback: используем базу данных
                participants = await db.get_chat_participants(chat_id)
                chat_participants_cache[cache_key] = participants
                logger.info(f"📊 Используем данные из БД: {len(participants)} участников")
        
        participants = chat_participants_cache[cache_key]
        
        # Проверяем, есть ли участники
        if not participants:
            logger.warning(f"⚠️ В чате {chat_id} нет участников для игры")
            return []
        
        logger.info(f"👥 Используем {len(participants)} участников чата {chat_id}")
        return participants
    
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
        "💩 Просто нажми кнопку ниже, чтобы метнуть говна в случайного участника чата.\n\n"
        "🎯 Или используй /go @username для метания в конкретного пользователя!\n\n"
        "🎲 Результат всегда случайный - можешь попасть в цель, промахнуться или устроить говнобум!\n\n"
        "🔥 Цель игры - превратить чат в говнохаос!\n"
        "💡 Работает в любом чате, даже с одним участником!",
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
        "• Нажми кнопку «💩 Метнуть говна» для случайной цели\n"
        "• Или используй /go @username для конкретной цели\n"
        "• Результат будет показан в чате\n"
        "• Работает в любом чате, даже с одним участником!\n\n"
        "📊 <b>Статистика:</b>\n"
        "• /stats - полная статистика чата, игровые достижения и ваши результаты\n"
        "• /ratings - топ игроков недели\n\n"
        "📊 <b>Команды:</b>\n"
        "/start - начать игру\n"
        "/help - показать эту справку\n"
        "/stats - показать полную статистику чата\n"
        "/ratings - показать рейтинги недели\n"
        "/refresh - обновить список участников\n"
        "/participants - показать список участников\n"
        "/go @username - метнуть говно в конкретного пользователя\n\n"
        "🔥 <b>Цель:</b> Устроить максимальный говнохаос в чате!"
    )
    
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Справка отправлена пользователю {user.username}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Показать полную статистику чата"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"📊 Команда /stats от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Получаем всю статистику
    chat_stats = await db.get_chat_stats(chat_id, days=30)
    game_stats = await db.get_game_stats(chat_id, days=30)
    
    if not chat_stats:
        stats_text = "📊 Пока нет данных для статистики. Начните играть!"
        await message.answer(stats_text, parse_mode="HTML", reply_markup=get_throw_button())
        return
    
    # Формируем общую статистику чата
    stats_text = f"📊 <b>ОБЩАЯ СТАТИСТИКА ЧАТА (30 дней):</b>\n\n"
    
    # Общие цифры
    total_throws = chat_stats.get('total_throws', 0)
    stats_text += f"🎯 <b>Всего бросков:</b> {total_throws}\n"
    

    
    # Топ метателей
    top_throwers = chat_stats.get('top_throwers', [])
    if top_throwers:
        stats_text += "\n🏆 <b>Топ метателей:</b>\n"
        for i, (username, throws) in enumerate(top_throwers, 1):
            stats_text += f"{i}. @{username}: {throws} бросков\n"
    
    # Топ страдальцев
    top_victims = chat_stats.get('top_victims', [])
    if top_victims:
        stats_text += "\n😵 <b>Топ страдальцев:</b>\n"
        for i, (username, hits) in enumerate(top_victims, 1):
            stats_text += f"{i}. @{username}: {hits} попаданий\n"
    
    # Топ неудачников
    top_losers = chat_stats.get('top_losers', [])
    if top_losers:
        stats_text += "\n🤡 <b>Топ неудачников:</b>\n"
        for i, (username, self_hits) in enumerate(top_losers, 1):
            stats_text += f"{i}. @{username}: {self_hits} раз сам себя обосрал\n"
    
    # Топ снайперов
    top_snipers = chat_stats.get('top_snipers', [])
    if top_snipers:
        stats_text += "\n🎯 <b>Топ снайперов:</b>\n"
        for i, (username, hits, total, accuracy) in enumerate(top_snipers, 1):
            stats_text += f"{i}. @{username}: {accuracy}% точность ({hits}/{total})\n"
    

    
    # Игровая статистика
    if game_stats:
        stats_text += "\n🎮 <b>ИГРОВАЯ СТАТИСТИКА:</b>\n"
        
        # Самый длинный говно-стрик
        longest_streak = game_stats.get('longest_streak')
        if longest_streak and longest_streak[1] > 0:
            username, streak = longest_streak
            stats_text += f"🔥 <b>Самый длинный говно-стрик:</b> @{username} ({streak} подряд)\n"
        
        # Говно-мастер
        shit_master = game_stats.get('shit_master')
        if shit_master:
            username, unique_targets = shit_master
            stats_text += f"👑 <b>Говно-мастер:</b> @{username} (метнул в {unique_targets} участников)\n"
        
        # Говно-везение
        lucky_bastard = game_stats.get('lucky_bastard')
        if lucky_bastard:
            username, times_hit, times_thrown = lucky_bastard
            stats_text += f"🍀 <b>Говно-везение:</b> @{username} (бросил {times_thrown}, получил {times_hit})\n"
        
        # Говно-маг
        shit_mage = game_stats.get('shit_mage')
        if shit_mage:
            username, special_effects = shit_mage
            stats_text += f"⚡ <b>Говно-маг:</b> @{username} ({special_effects} особых эффектов)\n"
    
    # Достижения и рейтинги
    stats_text += "\n🏅 <b>ДОСТИЖЕНИЯ И РЕЙТИНГИ:</b>\n"
    
    # Король говна (из существующей функции)
    ratings = await db.get_ratings(chat_id, days=7)
    if ratings.get('king'):
        username, hits = ratings['king']
        stats_text += f"👑 <b>Король говна недели:</b> @{username} ({hits} попаданий)\n"
    
    if ratings.get('victim'):
        username, hit_count = ratings['victim']
        stats_text += f"😵 <b>Главный обосранный недели:</b> @{username} ({hit_count} раз)\n"
    
    if ratings.get('idiot'):
        username, self_hits = ratings['idiot']
        stats_text += f"🤡 <b>Долбоёб недели:</b> @{username} ({self_hits} раз)\n"
    
    # Личная статистика пользователя
    user_stats = await db.get_user_stats(user.id)
    if user_stats:
        stats_text += f"\n👤 <b>ВАША СТАТИСТИКА:</b>\n"
        stats_text += f"🎯 Прямых попаданий: {user_stats['direct_hits']}\n"
        stats_text += f"🤡 Промахов: {user_stats['misses']}\n"
        stats_text += f"💩 Сам себя обосрал: {user_stats['self_hits']}\n"
        stats_text += f"😵 Страдал от других: {user_stats['times_hit']}\n"
        
        if user_stats['direct_hits'] + user_stats['misses'] + user_stats['self_hits'] > 0:
            accuracy = round((user_stats['direct_hits'] / (user_stats['direct_hits'] + user_stats['misses'] + user_stats['self_hits'])) * 100, 1)
            stats_text += f"🎯 Ваша точность: {accuracy}%\n"
        
        total_score = user_stats['direct_hits'] - user_stats['misses'] - user_stats['self_hits']
        stats_text += f"🔥 Общий счёт: {total_score}"
    
    await message.answer(stats_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Полная статистика отправлена пользователю {user.username}")

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
        # Проверяем, не устарел ли callback (увеличиваем время жизни до 24 часов)
        if callback.message.date and (datetime.now().replace(tzinfo=None) - callback.message.date.replace(tzinfo=None)).total_seconds() > 86400:
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
                await callback.answer("❌ Не удалось получить участников чата.")
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
        
        # Если кулдаун — показываем сообщение и удаляем через 5 сек
        if isinstance(game_result, dict) and game_result.get('error') == 'cooldown':
            cooldown_msg = await callback.message.answer(
                f"⏰ {game_result['message']}",
                reply_markup=get_throw_button()
            )
            await asyncio.sleep(5)
            try:
                await cooldown_msg.delete()
            except Exception:
                pass
            try:
                await callback.answer("⏰ Подожди немного…")
            except Exception:
                pass
            return
        
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
                
                # Если кулдаун — показываем сообщение и удаляем через 5 сек
                if isinstance(game_result, dict) and game_result.get('error') == 'cooldown':
                    cooldown_msg = await message.answer(
                        f"⏰ {game_result['message']}",
                        reply_markup=get_throw_button()
                    )
                    await asyncio.sleep(5)
                    try:
                        await cooldown_msg.delete()
                    except Exception:
                        pass
                    try:
                        await message.answer("⏰ Подожди немного…")
                    except Exception:
                        pass
                    return
                
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
                await message.answer("❌ Не удалось получить участников чата.")
    
    except Exception as e:
        logger.error(f"❌ Ошибка обработки ручного броска: {e}")

@dp.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    """Обновить список участников чата"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"🔄 Команда /refresh от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Очищаем кэш для этого чата (удаляем все ключи, связанные с этим чатом)
    keys_to_remove = [key for key in chat_participants_cache.keys() if key.startswith(f"{chat_id}_")]
    for key in keys_to_remove:
        del chat_participants_cache[key]
        logger.info(f"🗑️ Кэш участников чата {chat_id} очищен (ключ: {key})")
    
    # Получаем обновленный список участников
    participants = await get_chat_participants(chat_id)
    
    if participants:
        success_msg = await message.answer(
            f"✅ Список участников обновлен! Найдено {len(participants)} участников.",
            reply_markup=get_throw_button()
        )
        logger.info(f"✅ Список участников чата {chat_id} обновлен: {len(participants)} участников")
        
        # Удаляем сообщение об успехе через 10 секунд
        await asyncio.sleep(10)
        try:
            await success_msg.delete()
            logger.debug(f"🗑️ Сообщение об успехе команды /refresh от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об успехе от {user.username}: {e}")
    else:
        error_msg = await message.answer(
            "❌ Не удалось получить участников чата.",
            reply_markup=get_throw_button()
        )
        logger.warning(f"⚠️ Не удалось обновить список участников чата {chat_id}")
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
            logger.debug(f"🗑️ Сообщение об ошибке команды /refresh от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об ошибке от {user.username}: {e}")

@dp.message(Command("participants"))
async def cmd_participants(message: types.Message):
    """Показать список участников чата"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"👥 Команда /participants от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Получаем участников чата
    participants = await get_chat_participants(chat_id)
    
    if not participants:
        error_msg = await message.answer(
            "❌ Не удалось получить участников чата.",
            reply_markup=get_throw_button()
        )
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
            logger.debug(f"🗑️ Сообщение об ошибке команды /participants от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об ошибке от {user.username}: {e}")
        
        return
    
    # Формируем список участников
    participants_text = f"👥 <b>Участники чата ({len(participants)}):</b>\n\n"
    
    for i, (user_id, username) in enumerate(participants, 1):
        display_name = f"@{username}" if username and not username.startswith("user") else username
        participants_text += f"{i}. {display_name}\n"
    
    participants_text += f"\n💡 Используйте команду /go @username для метания в конкретного пользователя"
    
    participants_msg = await message.answer(
        participants_text,
        parse_mode="HTML",
        reply_markup=get_throw_button()
    )
    
    logger.info(f"✅ Список участников отправлен пользователю {user.username}")
    
    # Удаляем сообщение со списком участников через 15 секунд
    await asyncio.sleep(15)
    try:
        await participants_msg.delete()
        logger.debug(f"🗑️ Список участников от {user.username} удален")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить список участников от {user.username}: {e}")

@dp.message(Command("go"))
async def cmd_go(message: types.Message):
    """Метнуть говно в конкретного пользователя"""
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"💩 Команда /go от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Проверяем, есть ли аргумент (username цели)
    if not message.text or len(message.text.split()) < 2:
        error_msg = await message.answer(
            "💩 Использование: /go @username\n"
            "Пример: /go @ivan\n\n"
            "🎯 Метает говно в указанного пользователя!",
            reply_markup=get_throw_button()
        )
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
            logger.debug(f"🗑️ Сообщение об ошибке команды /go от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об ошибке от {user.username}: {e}")
        
        return
    
    # Извлекаем username цели
    target_username = message.text.split()[1].lstrip('@')
    logger.info(f"🎯 Цель команды /go: @{target_username}")
    
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
        error_msg = await message.answer(
            "❌ Не удалось получить участников чата.",
            reply_markup=get_throw_button()
        )
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
            logger.debug(f"🗑️ Сообщение об ошибке команды /go от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об ошибке от {user.username}: {e}")
        
        return
    
    # Ищем цель по username
    target_user = None
    for user_id, username in participants:
        if username.lower() == target_username.lower() or f"@{username.lower()}" == f"@{target_username.lower()}":
            target_user = (user_id, username)
            break
    
    if not target_user:
        error_msg = await message.answer(
            f"❌ Пользователь @{target_username} не найден в чате.\n\n"
            "💡 Убедитесь, что:\n"
            "• Username написан правильно\n"
            "• Пользователь находится в этом чате\n"
            "• Попробуйте команду /refresh для обновления списка",
            reply_markup=get_throw_button()
        )
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
            logger.debug(f"🗑️ Сообщение об ошибке команды /go от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об ошибке от {user.username}: {e}")
        
        return
    
    # Проверяем, что цель не является самим метателем
    if target_user[0] == user.id:
        error_msg = await message.answer(
            "🤡 Нельзя метать говно в самого себя! Попробуйте другую цель.",
            reply_markup=get_throw_button()
        )
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
            logger.debug(f"🗑️ Сообщение об ошибке команды /go от {user.username} удалено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить сообщение об ошибке от {user.username}: {e}")
        
        return
    
    # Обрабатываем бросок в конкретную цель
    game_result = game_logic.process_throw_at_target(
        initiator_id=user.id,
        initiator_username=user.username or f"user{user.id}",
        target_id=target_user[0],
        target_username=target_user[1],
        chat_id=chat_id
    )
    
    # Если кулдаун — показываем сообщение и удаляем через 5 сек
    if isinstance(game_result, dict) and game_result.get('error') == 'cooldown':
        cooldown_msg = await message.answer(
            f"⏰ {game_result['message']}",
            reply_markup=get_throw_button()
        )
        await asyncio.sleep(5)
        try:
            await cooldown_msg.delete()
        except Exception:
            pass
        return
    
    # Проверяем на ошибки (кулдаун, самоцель и т.д.)
    if 'error' in game_result:
        error_msg = await message.answer(
            game_result['message'],
            reply_markup=get_throw_button()
        )
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
        except Exception:
            pass
        return
    
    # Обновляем расширенные данные пользователя в БД
    await db.update_user_heat(user.id, game_result.get('heat_at_throw', 0))
    await db.update_score(user.id, game_result.get('score_delta', 0))
    if game_result.get('role_used'):
        expires_at = datetime.now() + timedelta(seconds=3600)  # 1 час
        await db.update_user_role(user.id, game_result['role_used'], expires_at.isoformat())
    await db.update_user_last_throw(user.id)
    
    # Добавляем событие в базу с новыми полями
    await db.add_event(
        initiator_id=user.id,
        target_id=target_user[0],
        outcome=game_result['outcome'],
        chat_id=chat_id,
        role_used=game_result.get('role_used'),
        stacks_at_hit=game_result.get('focus_stacks', 0),
        heat_at_hit=game_result.get('heat_at_throw', 0),
        was_reflect=0,  # TODO: реализовать отражение
        targets_json=str(game_result['targets'])
    )
    
    # Обновляем фокус в БД
    focus_stacks = game_result.get('focus_stacks', 0)
    penalty_until = None
    if focus_stacks > 3:  # Штраф за фокус
        penalty_until = (datetime.now() + timedelta(seconds=300)).isoformat()  # 5 минут
    await db.set_focus(user.id, target_user[0], chat_id, focus_stacks, penalty_until)
    
    # Обновляем базовую статистику
    await db.update_user_stats(user.id, game_result['outcome'], is_target=False)
    await db.update_user_stats(target_user[0], game_result['outcome'], is_target=True)
    
    # Формируем сообщение с результатом
    emoji = game_logic.get_emoji_for_outcome(game_result['outcome'])
    result_message = f"{emoji} {game_result['message']}"
    
    # Добавляем информацию о роли и heat
    if game_result.get('role_used'):
        role_names = {
            'sniper': '🎯 Снайпер',
            'bombardier': '💣 Бомбардир', 
            'defender': '🛡️ Оборонец'
        }
        role_name = role_names.get(game_result['role_used'], game_result['role_used'])
        result_message += f"\n\n🎭 {role_name}"
    
    if game_result.get('heat_at_throw', 0) > 50:
        result_message += f"\n🔥 Репутация агрессора: {game_result['heat_at_throw']}/100"
    
    # Отправляем результат
    await message.answer(
        result_message,
        reply_markup=get_throw_button()
    )
    
    # Отправляем публичные сигналы
    if game_result.get('public_signals'):
        signals = game_result['public_signals']
        if signals.get('call_to_action'):
            signals_msg = await message.answer(
                f"📢 {signals['call_to_action']}",
                reply_markup=get_throw_button()
            )
            # Удаляем сигналы через 15 секунд
            await asyncio.sleep(15)
            try:
                await signals_msg.delete()
            except Exception:
                pass
    
    # Удаляем сообщение команды через 3 секунды
    await asyncio.sleep(GAME_SETTINGS['message_delete_delay'])
    try:
        await message.delete()
        logger.debug(f"🗑️ Сообщение команды /go от {user.username} удалено")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить сообщение команды /go от {user.username}: {e}")
        pass  # Игнорируем ошибки удаления
    
    logger.info(f"✅ Целевой бросок завершен: {user.username} -> {target_user[1]} -> {game_result['outcome']}")

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

