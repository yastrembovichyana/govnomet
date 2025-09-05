import asyncio
import random
import logging
from datetime import datetime, timedelta, timezone
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

# Обработчик команды /go (должен быть первым!)
@dp.message(Command("go"))
async def cmd_go(message: types.Message):
    """Метнуть говно в конкретного пользователя"""
    schedule_auto_delete(message, 10)
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"💩 Команда /go от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Регистрируем автора
    _record_seen_user(chat_id, user)

    # Если аргумент не указан, но это ответ на сообщение — целимся в автора реплая
    if (not message.text or len(message.text.split()) < 2) and getattr(message, "reply_to_message", None):
        # Добавляем пользователя в базу
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        participants = await get_chat_participants(chat_id)
        reply_user = message.reply_to_message.from_user
        target_id = reply_user.id
        target_username = reply_user.username or f"user{reply_user.id}"

        # Если цели нет в списке, всё равно бьём по реплаю
        game_result = game_logic.process_throw_at_target(
            initiator_id=user.id,
            initiator_username=user.username or f"user{user.id}",
            target_id=target_id,
            target_username=target_username,
            chat_id=chat_id
        )

        # Если кулдаун — показываем сообщение
        if isinstance(game_result, dict) and game_result.get('error') == 'cooldown':
            cooldown_msg = await message.answer(
                f"⏰ {game_result['message']}",
                reply_markup=get_throw_button()
            )
            schedule_auto_delete(cooldown_msg, 5)
            try:
                hint_msg = await message.answer("⏰ Подожди немного…")
                schedule_auto_delete(hint_msg, 5)
            except Exception:
                pass
            return

        for target in game_result['targets']:
            await db.add_event(
                initiator_id=user.id,
                target_id=target[0],
                outcome=game_result['outcome'],
                chat_id=chat_id
            )
        await db.update_user_stats(user.id, game_result['outcome'], is_target=False)
        for target in game_result['targets']:
            await db.update_user_stats(target[0], game_result['outcome'], is_target=True)
        emoji = game_logic.get_emoji_for_outcome(game_result['outcome'])
        result_message = f"{emoji} {game_result['message']}"
        # Добавляем роль к результату
        if game_result.get('role_used'):
            role_names = {
                'sniper': '🎯 Снайпер',
                'bombardier': '💣 Бомбардир',
                'defender': '🛡️ Оборонец',
                'drunk_sniper': '🍺🎯 Снайпер‑пьяница',
                'berserker': '🪓 Берсерк',
                'trickster': '🃏 Трикстер',
                'magnet': '🧲 Магнит',
                'saboteur': '🕳️ Саботажник',
                'oracle': '🔮 Оракул',
                'pyromaniac': '🔥 Пироман',
                'shieldbearer': '🛡️ Щитоносец',
                'collector': '📎 Коллектор',
                'teleporter': '🌀 Телепортер',
                'rocketeer': '🚀 Говноракетчик',
                'snot_sniper': '🤧 Сопля‑снайпер',
                'acid_clown': '🧪🤡 Кислотный клоун',
                'counter_guru': '🔁 Обратка‑гуру'
            }
            role_name = role_names.get(game_result['role_used'], '🎭 Неизвестная роль')
            result_message += f"\n\n🎭 Роль метателя: {role_name}"

        # Добавляем публичные сигналы в то же сообщение
        if game_result.get('public_signals'):
            extras = _format_public_signals(game_result['public_signals'])
            if extras:
                result_message += "\n\n" + "\n".join([f"📢 {line}" for line in extras])

        await message.answer(result_message, reply_markup=get_throw_button_with_role(game_result.get('role_used')))
        return

    # Если аргумент не указан — метаем случайно (как кнопкой)
    if not message.text or len(message.text.split()) < 2:
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
            # Фоллбэк: берём хотя бы инициатора, чтобы бросок всегда сработал
            initiator_name = user.username or f"user{user.id}"
            participants = [(user.id, initiator_name)]
            logger.info("🧩 Нет участников — используем инициатора как единственную цель для случайного броска")

        # Пытаемся выбрать рандомную цель (не инициатора). Если никого, оставим текущую механику
        available_targets = [p for p in participants if p[0] != user.id]
        if available_targets:
            random_target_id, random_target_username = random.choice(available_targets)
            logger.info(f"🎯 /go без аргумента: выбран случайный таргет @{random_target_username} ({random_target_id})")
            game_result = game_logic.process_throw_at_target(
                initiator_id=user.id,
                initiator_username=user.username or f"user{user.id}",
                target_id=random_target_id,
                target_username=random_target_username,
                chat_id=chat_id
            )
        else:
            # Обрабатываем случайный бросок по старой логике (когда один в чате)
            game_result = game_logic.process_throw(
                initiator_id=user.id,
                initiator_username=user.username or f"user{user.id}",
                participants=participants,
                chat_id=chat_id
            )
        
        # Если кулдаун — показываем сообщение
        if isinstance(game_result, dict) and game_result.get('error') == 'cooldown':
            cooldown_msg = await message.answer(
                f"⏰ {game_result['message']}",
                reply_markup=get_throw_button()
            )
            schedule_auto_delete(cooldown_msg, 5)
            try:
                hint_msg = await message.answer("⏰ Подожди немного…")
                schedule_auto_delete(hint_msg, 5)
            except Exception:
                pass
            return
        
        # Сохраняем событие(я)
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
        
        # Сообщение результата
        emoji = game_logic.get_emoji_for_outcome(game_result['outcome'])
        result_message = f"{emoji} {game_result['message']}"
        # Добавляем роль к результату
        if game_result.get('role_used'):
            role_names = {
                'sniper': '🎯 Снайпер',
                'bombardier': '💣 Бомбардир',
                'defender': '🛡️ Оборонец',
                'drunk_sniper': '🍺🎯 Снайпер‑пьяница',
                'berserker': '🪓 Берсерк',
                'trickster': '🃏 Трикстер',
                'magnet': '🧲 Магнит',
                'saboteur': '🕳️ Саботажник',
                'oracle': '🔮 Оракул',
                'pyromaniac': '🔥 Пироман',
                'shieldbearer': '🛡️ Щитоносец',
                'collector': '📎 Коллектор',
                'teleporter': '🌀 Телепортер',
                'rocketeer': '🚀 Говноракетчик',
                'snot_sniper': '🤧 Сопля‑снайпер',
                'acid_clown': '🧪🤡 Кислотный клоун',
                'counter_guru': '🔁 Обратка‑гуру'
            }
            role_name = role_names.get(game_result['role_used'], '🎭 Неизвестная роль')
            result_message += f"\n\n🎭 Роль метателя: {role_name}"

        # Публичные сигналы (в том же сообщении)
        if game_result.get('public_signals'):
            extras = _format_public_signals(game_result['public_signals'])
            if extras:
                result_message += "\n\n" + "\n".join([f"📢 {line}" for line in extras])
        await message.answer(
            result_message,
            reply_markup=get_throw_button_with_role(game_result.get('role_used'))
        )
        return
    
    # Извлекаем цель из entities/текста
    target_username = None
    # 1) entities: mention (@name) или text_mention (прямой пользователь)
    try:
        if message.entities:
            for ent in message.entities:
                if ent.type in {"mention", "text_mention"}:
                    if ent.type == "mention":
                        target_username = message.text[ent.offset: ent.offset + ent.length]
                        target_username = target_username.lstrip('@')
                        break
                    elif ent.type == "text_mention" and ent.user:
                        target_username = str(ent.user.id)
                        break
    except Exception:
        pass
    # 2) если не нашли — поддержим формат без пробела: /go@user
    if not target_username and message.text and message.text.startswith('/go@'):
        after = message.text[len('/go@'):]
        target_username = after.split()[0].strip(',.;:!?)(')
    # 3) если не нашли — берём второй токен
    if not target_username:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            target_username = parts[1].strip()
    # Чистим от пунктуации по краям и @
    if target_username:
        target_username = target_username.strip().strip(',.;:!?)(').lstrip('@')
    else:
        # Если вообще ничего не удалось извлечь — fallback в случайный бросок
        await message.answer("🤷 Не понял, в кого метать. Кидаю наугад.")
        # Выполняем логику случайного броска напрямую
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        participants = await get_chat_participants(chat_id)
        if not participants:
            initiator_name = user.username or f"user{user.id}"
            participants = [(user.id, initiator_name)]
        available_targets = [p for p in participants if p[0] != user.id]
        if available_targets:
            random_target_id, random_target_username = random.choice(available_targets)
            game_result = game_logic.process_throw_at_target(
                initiator_id=user.id,
                initiator_username=user.username or f"user{user.id}",
                target_id=random_target_id,
                target_username=random_target_username,
                chat_id=chat_id
            )
        else:
            game_result = game_logic.process_throw(
                initiator_id=user.id,
                initiator_username=user.username or f"user{user.id}",
                participants=participants,
                chat_id=chat_id
            )
        if isinstance(game_result, dict) and game_result.get('error') == 'cooldown':
            await message.answer(f"⏰ {game_result['message']}", reply_markup=get_throw_button())
            try:
                await message.answer("⏰ Подожди немного…")
            except Exception:
                pass
            return
        for target in game_result['targets']:
            await db.add_event(
                initiator_id=user.id,
                target_id=target[0],
                outcome=game_result['outcome'],
                chat_id=chat_id
            )
        await db.update_user_stats(user.id, game_result['outcome'], is_target=False)
        for target in game_result['targets']:
            await db.update_user_stats(target[0], game_result['outcome'], is_target=True)
        emoji = game_logic.get_emoji_for_outcome(game_result['outcome'])
        result_message = f"{emoji} {game_result['message']}"
        
        # Добавляем роль к результату
        if game_result.get('role_used'):
            role_names = {
                'sniper': '🎯 Снайпер',
                'bombardier': '💣 Бомбардир',
                'defender': '🛡️ Оборонец',
                'drunk_sniper': '🍺🎯 Снайпер‑пьяница',
                'berserker': '🪓 Берсерк',
                'trickster': '🃏 Трикстер',
                'magnet': '🧲 Магнит',
                'saboteur': '🕳️ Саботажник',
                'oracle': '🔮 Оракул',
                'pyromaniac': '🔥 Пироман',
                'shieldbearer': '🛡️ Щитоносец',
                'collector': '📎 Коллектор',
                'teleporter': '🌀 Телепортер',
                'rocketeer': '🚀 Говноракетчик',
                'snot_sniper': '🤧 Сопля‑снайпер',
                'acid_clown': '🧪🤡 Кислотный клоун',
                'counter_guru': '🔁 Обратка‑гуру'
            }
            role_name = role_names.get(game_result['role_used'], '🎭 Неизвестная роль')
            result_message += f"\n\n🎭 Роль метателя: {role_name}"
        
        # Добавляем публичные сигналы в то же сообщение
        if game_result.get('public_signals'):
            extras = _format_public_signals(game_result['public_signals'])
            if extras:
                result_message += "\n\n" + "\n".join([f"📢 {line}" for line in extras])

        await message.answer(result_message, reply_markup=get_throw_button_with_role(game_result.get('role_used')))
        return
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
    # Даже если участников нет, продолжаем: позволяем кидать в произвольный username (виртуальная цель)
    
    # Ищем цель по имени или username
    target_user = None
    # Сначала пробуем найти по ID, если аргумент — число
    if target_username.isdigit():
        numeric_id = int(target_username)
        for user_id, display_name in participants:
            if user_id == numeric_id:
                target_user = (user_id, display_name or f"user{user_id}")
                break
    # Затем ищем по username/отображаемому имени (без учёта регистра)
    if target_user is None:
        for user_id, display_name in participants:
            if not display_name:
                continue
            name_l = display_name.lower()
            arg_l = target_username.lower()
            if name_l == arg_l or name_l.startswith(arg_l):
                target_user = (user_id, display_name)
                break
    
    if not target_user:
        # Разрешаем метнуть в любого username: создаём виртуального пользователя
        virtual_id = _virtual_user_id_from_username(target_username.lower())
        target_user = (virtual_id, target_username)
        logger.info(f"🧩 Цель @{target_username} не найдена в участниках. Используем виртуальный ID {virtual_id}")
        
        # Сохраняем в seen и в БД (как пользователя без активности)
        chat_seen_users.setdefault(chat_id, {})[virtual_id] = target_username
        try:
            await db.add_user(user_id=virtual_id, username=target_username)
        except Exception:
            pass
    
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
            'defender': '🛡️ Оборонец',
            'drunk_sniper': '🍺🎯 Снайпер‑пьяница',
            'berserker': '🪓 Берсерк',
            'trickster': '🃏 Трикстер',
            'magnet': '🧲 Магнит',
            'saboteur': '🕳️ Саботажник',
            'oracle': '🔮 Оракул',
            'pyromaniac': '🔥 Пироман',
            'shieldbearer': '🛡️ Щитоносец',
            'collector': '📎 Коллектор',
            'teleporter': '🌀 Телепортер',
            'rocketeer': '🚀 Говноракетчик',
            'snot_sniper': '🤧 Сопля‑снайпер',
            'acid_clown': '🧪🤡 Кислотный клоун',
            'counter_guru': '🔁 Обратка‑гуру'
        }
        role_name = role_names.get(game_result['role_used'], '🎭 Неизвестная роль')
        result_message += f"\n\n🎭 Роль метателя: {role_name}"
    
    if game_result.get('heat_at_throw', 0) > 50:
        result_message += f"\n🔥 Репутация агрессора: {game_result['heat_at_throw']}/100"
    
    # Добавляем публичные сигналы в то же сообщение
    if game_result.get('public_signals'):
        extras = _format_public_signals(game_result['public_signals'])
        if extras:
            result_message += "\n\n" + "\n".join([f"📢 {line}" for line in extras])

    # Отправляем результат
    await message.answer(
        result_message,
        reply_markup=get_throw_button_with_role(game_result.get('role_used'))
    )
    
    # Больше не удаляем сообщение команды /go
    
    logger.info(f"✅ Целевой бросок завершен: {user.username} -> {target_user[1]} -> {game_result['outcome']}")

# Общий обработчик сообщений (должен быть после команд!)
@dp.message(F.text & ~F.text.startswith('/'))
async def _collect_seen_users(message: types.Message):
    """Тихий сбор авторов сообщений как участников (особенно для basic-групп)."""
    try:
        if message and message.from_user and message.chat:
            _record_seen_user(message.chat.id, message.from_user)
    except Exception:
        pass

# Кэш участников чатов (в реальности лучше получать через Telegram API)
chat_participants_cache = {}
"""Кэш участников на основе API/БД с тайм-слотом ~10 минут"""

# Резервный сбор участников для basic-групп: по сообщениям и событиям
chat_seen_users: dict[int, dict[int, str]] = {}
"""chat_id -> { user_id: display_name }"""

def _display_name_from_user(user: types.User) -> str:
    """Возвращает идентификатор для упоминаний: только username или user{id}."""
    return user.username or f"user{user.id}"

def _record_seen_user(chat_id: int, user: types.User) -> None:
    if chat_id not in chat_seen_users:
        chat_seen_users[chat_id] = {}
    chat_seen_users[chat_id][user.id] = _display_name_from_user(user)

def _virtual_user_id_from_username(username: str) -> int:
    """Генерирует стабильный виртуальный user_id по username (отрицательный ID)."""
    import hashlib
    base = int(hashlib.md5(username.encode('utf-8')).hexdigest()[:8], 16)
    return -abs(base)

def get_throw_button() -> InlineKeyboardMarkup:
    """Создание кнопки для броска говна"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💩 Метнуть говна", callback_data="throw_shit"))
    return builder.as_markup()

def get_throw_button_with_role(role_used: str = None) -> InlineKeyboardMarkup:
    """Создание кнопки для броска говна с кнопкой описания роли"""
    builder = InlineKeyboardBuilder()
    
    if role_used:
        builder.add(InlineKeyboardButton(text="🎭 Описание роли", callback_data=f"role_info:{role_used}"))
    
    builder.add(InlineKeyboardButton(text="💩 Метнуть говна", callback_data="throw_shit"))
    
    return builder.as_markup()

def _format_public_signals(signals: dict) -> list[str]:
    messages: list[str] = []
    try:
        # Добавляем все callouts (включая фразы про фокус и heat)
        for line in signals.get('callouts', []):
            messages.append(line.replace('/go @', '/go@'))
        
        # Добавляем call_to_action (основной призыв к действию)
        if signals.get('call_to_action'):
            messages.append(signals['call_to_action'].replace('/go @', '/go@'))
            
    except Exception:
        pass
    return messages

async def _auto_delete(msg: types.Message, delay: int = 5):
    try:
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except Exception:
            pass
    except Exception:
        pass

def schedule_auto_delete(msg: types.Message, delay: int = 5):
    try:
        asyncio.create_task(_auto_delete(msg, delay))
    except Exception:
        pass

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
                # В Bot API нет полноценного метода перечисления всех членов basic-группы.
                # Если провалимся — используем fallback ниже.
                async for member in bot.get_chat_members(chat_id, limit=200):  # может бросить исключение в basic-группах
                    if not member.user.is_bot:
                        username = member.user.username or f"user{member.user.id}"
                        participants.append((member.user.id, username))
                
                chat_participants_cache[cache_key] = participants
                logger.info(f"✅ Получено {len(participants)} участников чата {chat_id} через API")
                
            except Exception as api_error:
                logger.warning(f"⚠️ Не удалось получить участников через API: {api_error}")
                # Fallback: используем базу данных
                participants = await db.get_chat_participants(chat_id)
                # Если и в БД пусто (новый чат), используем собранных по сообщениям
                if not participants:
                    seen = chat_seen_users.get(chat_id, {})
                    participants = [(uid, name) for uid, name in seen.items()]
                    if participants:
                        logger.info(f"🧩 Используем участников, собранных по сообщениям: {len(participants)}")
                chat_participants_cache[cache_key] = participants
                logger.info(f"📊 Используем данные из БД/seen: {len(participants)} участников")
        
        participants = chat_participants_cache[cache_key]

        # Если кэш пустой — попробуем собрать из seen/БД прямо сейчас
        if not participants:
            seen_now = chat_seen_users.get(chat_id, {})
            if seen_now:
                participants = [(uid, name) for uid, name in seen_now.items()]
                chat_participants_cache[cache_key] = participants
                logger.info(f"🧩 Обновили кэш участников из seen: {len(participants)}")
            else:
                # Последняя попытка — взять из БД
                participants = await db.get_chat_participants(chat_id)
                if participants:
                    chat_participants_cache[cache_key] = participants
                    logger.info(f"📦 Обновили кэш участников из БД: {len(participants)}")

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
    # Автоудаление пользовательского запроса
    schedule_auto_delete(message, 3)
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"🚀 Команда /start от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Регистрируем создателя сообщения как увиденного участника (для basic-групп)
    _record_seen_user(chat_id, user)
    
    await message.answer(
        "🎯 Добро пожаловать в игру «ГовноМёт»!\n\n"
        "💩 Просто нажми кнопку ниже, чтобы метнуть говна в случайного участника чата.\n\n"
        "🎯 Или используй /go@имя для метания в конкретного пользователя!\n\n"
        "🎲 Результат всегда случайный - можешь попасть в цель, промахнуться или устроить говнобум!\n\n"
        "🔥 Цель игры - превратить чат в говнохаос!\n"
        "💡 Работает в любом чате, даже с одним участником!",
        reply_markup=get_throw_button()
    )
    
    logger.info(f"✅ Приветственное сообщение отправлено пользователю {user.username}")

# Дублирующие хендлеры для случаев с упоминанием бота (/cmd@Bot) и разных типов чатов
@dp.message(F.text.regexp(r"^/start(?:@[A-Za-z0-9_]+)?(?:\s|$)"))
async def cmd_start_alias(message: types.Message):
    return await cmd_start(message)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    schedule_auto_delete(message, 3)
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"❓ Команда /help от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    help_text = (
        "🎯 <b>ГовноМёт - правила игры:</b>\n\n"
        "💩 <b>Как играть:</b>\n"
        "• Нажми кнопку «💩 Метнуть говна» для случайной цели\n"
        "• Или используй /go@имя для конкретной цели\n"
        "• Результат будет показан в чате\n"
        "• Работает в любом чате, даже с одним участником!\n\n"
        "📊 <b>Статистика:</b>\n"
        "• /stats - полная статистика чата и ваши результаты\n\n"
        "📊 <b>Команды:</b>\n"
        "/start - начать игру\n"
        "/help - показать эту справку\n"
        "/stats - показать полную статистику чата\n"
        ""
        "/refresh - обновить список участников\n"
        "/participants - показать список участников\n"
        "/go@имя - метнуть говно в конкретного пользователя\n\n"
        "🔥 <b>Цель:</b> Устроить максимальный говнохаос в чате!"
    )
    
    # Регистрируем автора
    _record_seen_user(chat_id, user)
    
    await message.answer(help_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Справка отправлена пользователю {user.username}")

@dp.message(F.text.regexp(r"^/help(?:@[A-Za-z0-9_]+)?(?:\s|$)"))
async def cmd_help_alias(message: types.Message):
    return await cmd_help(message)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Показать полную статистику чата"""
    schedule_auto_delete(message, 3)
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
    
    # Рейтинги и достижения удалены
    
    # Личная статистика пользователя
    user_stats = await db.get_user_stats(user.id, chat_id)
    if user_stats:
        stats_text += f"\n👤 <b>ВАША СТАТИСТИКА:</b>\n"
        stats_text += f"🎯 Прямых попаданий: {user_stats['direct_hits']}\n"
        stats_text += f"💩 Сам себя обосрал: {user_stats['self_hits']}\n"
        stats_text += f"😵 Страдал от других: {user_stats['times_hit']}\n"
        
        total_throws = user_stats['direct_hits'] + user_stats['self_hits']
        if total_throws > 0:
            accuracy = round((user_stats['direct_hits'] / total_throws) * 100, 1)
            stats_text += f"🎯 Ваша точность: {accuracy}%\n"
        
        total_score = user_stats['direct_hits'] - user_stats['self_hits']
        stats_text += f"🔥 Общий счёт: {total_score}"
    
    await message.answer(stats_text, parse_mode="HTML", reply_markup=get_throw_button())
    logger.info(f"✅ Полная статистика отправлена пользователю {user.username}")

@dp.message(F.text.regexp(r"^/stats(?:@[A-Za-z0-9_]+)?(?:\s|$)"))
async def cmd_stats_alias(message: types.Message):
    return await cmd_stats(message)

# Команда /ratings удалена

@dp.callback_query(F.data.startswith("role_info:"))
async def show_role_info(callback: types.CallbackQuery):
    """Показать описание роли"""
    try:
        role_key = callback.data.split(":", 1)[1]
        user = callback.from_user
        chat_id = callback.message.chat.id
        
        logger.info(f"🎭 Запрос описания роли {role_key} от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
        
        # Получаем информацию о роли из БД
        role_info = await db.get_role_info(role_key)
        
        if not role_info:
            await callback.answer("❌ Информация о роли не найдена")
            return
        
        # Формируем описание роли
        role_text = f"🎭 <b>{role_info['role_name']}</b>\n"
        role_text += f"📝 <b>Описание:</b> {role_info['description']}\n"
        role_text += f"⚡ <b>Бонусы:</b> {role_info['bonuses']}\n"
        
        if role_info['penalties']:
            role_text += f"⚠️ <b>Штрафы:</b> {role_info['penalties']}\n"
        
        if role_info['special_effects']:
            role_text += f"✨ <b>Особые эффекты:</b> {role_info['special_effects']}\n"
        
        role_text += f"🎯 <b>Стиль игры:</b> {role_info['style']}"
        
        # Отправляем описание роли
        role_msg = await callback.message.answer(role_text, parse_mode="HTML")
        
        # Автоудаление через 30 секунд
        schedule_auto_delete(role_msg, 30)
        
        # Отвечаем на callback
        try:
            await callback.answer("🎭 Описание роли показано")
        except Exception:
            logger.warning("⚠️ Не удалось ответить на callback (возможно, устарел)")
        
        logger.info(f"✅ Описание роли {role_key} отправлено пользователю {user.username}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка показа описания роли: {e}")
        try:
            await callback.answer("❌ Ошибка получения информации о роли")
        except Exception:
            logger.warning("⚠️ Не удалось ответить на callback (возможно, устарел)")

@dp.callback_query(F.data == "throw_shit")
async def process_throw_shit(callback: types.CallbackQuery):
    """Обработка нажатия кнопки броска говна"""
    try:
        # Проверяем, не устарел ли callback (увеличиваем время жизни до 24 часов)
        if callback.message.date:
            now_utc = datetime.now(timezone.utc)
            msg_date = callback.message.date
            if (now_utc - msg_date).total_seconds() > 86400:
                logger.warning(f"⚠️ Получен устаревший callback от {callback.from_user.username}")
                try:
                    await callback.answer("⚠️ Кнопка устарела, попробуйте снова")
                except Exception:
                    pass
                return
        
        user = callback.from_user
        chat_id = callback.message.chat.id

        # Запоминаем пользователя как участника (basic-группы)
        _record_seen_user(chat_id, user)
        
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
            schedule_auto_delete(cooldown_msg, 5)
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
        
        # Добавляем роль к результату
        if game_result.get('role_used'):
            role_names = {
                'sniper': '🎯 Снайпер',
                'bombardier': '💣 Бомбардир',
                'defender': '🛡️ Оборонец',
                'drunk_sniper': '🍺🎯 Снайпер‑пьяница',
                'berserker': '🪓 Берсерк',
                'trickster': '🃏 Трикстер',
                'magnet': '🧲 Магнит',
                'saboteur': '🕳️ Саботажник',
                'oracle': '🔮 Оракул',
                'pyromaniac': '🔥 Пироман',
                'shieldbearer': '🛡️ Щитоносец',
                'collector': '📎 Коллектор',
                'teleporter': '🌀 Телепортер',
                'rocketeer': '🚀 Говноракетчик',
                'snot_sniper': '🤧 Сопля‑снайпер',
                'acid_clown': '🧪🤡 Кислотный клоун',
                'counter_guru': '🔁 Обратка‑гуру'
            }
            role_name = role_names.get(game_result['role_used'], '🎭 Неизвестная роль')
            result_message += f"\n\n🎭 Роль метателя: {role_name}"

        # Добавляем публичные сигналы в то же сообщение
        if game_result.get('public_signals'):
            extras = _format_public_signals(game_result['public_signals'])
            if extras:
                result_message += "\n\n" + "\n".join([f"📢 {line}" for line in extras])

        # Отправляем результат
        await callback.message.answer(
            result_message,
            reply_markup=get_throw_button_with_role(game_result.get('role_used'))
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
        schedule_auto_delete(message, 3)
        user = message.from_user
        chat_id = message.chat.id

        _record_seen_user(chat_id, user)
        
        logger.info(f"💩 Ручной ввод команды от {user.username} (ID: {user.id}) в чате {chat_id}: {message.text}")
        
        # Извлекаем username цели
        text = message.text.lower()
        if "кинуть говно в @" in text:
            target_username = text.split("кинуть говно в @")[1].split()[0]
            logger.debug(f"🎯 Цель ручного броска: @{target_username}")
            
            # Больше не удаляем пользовательские сообщения
            
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
                    await message.answer(
                        f"⏰ {game_result['message']}",
                        reply_markup=get_throw_button()
                    )
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
                
                # Добавляем роль к результату
                if game_result.get('role_used'):
                    role_names = {
                        'sniper': '🎯 Снайпер',
                        'bombardier': '💣 Бомбардир',
                        'defender': '🛡️ Оборонец',
                        'drunk_sniper': '🍺🎯 Снайпер‑пьяница',
                        'berserker': '🪓 Берсерк',
                        'trickster': '🃏 Трикстер',
                        'magnet': '🧲 Магнит',
                        'saboteur': '🕳️ Саботажник',
                        'oracle': '🔮 Оракул',
                        'pyromaniac': '🔥 Пироман',
                        'shieldbearer': '🛡️ Щитоносец',
                        'collector': '📎 Коллектор',
                        'teleporter': '🌀 Телепортер',
                        'rocketeer': '🚀 Говноракетчик',
                        'snot_sniper': '🤧 Сопля‑снайпер',
                        'acid_clown': '🧪🤡 Кислотный клоун',
                        'counter_guru': '🔁 Обратка‑гуру'
                    }
                    role_name = role_names.get(game_result['role_used'], '🎭 Неизвестная роль')
                    result_message += f"\n\n🎭 Роль метателя: {role_name}"
                
                # Добавляем публичные сигналы в то же сообщение
                if game_result.get('public_signals'):
                    extras = _format_public_signals(game_result['public_signals'])
                    if extras:
                        result_message += "\n\n" + "\n".join([f"📢 {line}" for line in extras])
                
                # Отправляем результат
                await message.answer(
                    result_message,
                    reply_markup=get_throw_button_with_role(game_result.get('role_used'))
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
    schedule_auto_delete(message, 3)
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"🔄 Команда /refresh от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Регистрируем автора
    _record_seen_user(chat_id, user)

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
        
        # Больше не удаляем сообщение об успехе
    else:
        error_msg = await message.answer(
            "❌ Не удалось получить участников чата.",
            reply_markup=get_throw_button()
        )
        logger.warning(f"⚠️ Не удалось обновить список участников чата {chat_id}")
        
        # Больше не удаляем сообщение об ошибке

@dp.message(F.text.regexp(r"^/refresh(?:@[A-Za-z0-9_]+)?(?:\s|$)"))
async def cmd_refresh_alias(message: types.Message):
    return await cmd_refresh(message)

@dp.message(Command("participants"))
async def cmd_participants(message: types.Message):
    """Показать список участников чата"""
    schedule_auto_delete(message, 3)
    user = message.from_user
    chat_id = message.chat.id
    
    logger.info(f"👥 Команда /participants от пользователя {user.username} (ID: {user.id}) в чате {chat_id}")
    
    # Регистрируем автора
    _record_seen_user(chat_id, user)

    # Получаем участников чата
    participants = await get_chat_participants(chat_id)
    
    if not participants:
        error_msg = await message.answer(
            "❌ Не удалось получить участников чата.",
            reply_markup=get_throw_button()
        )
        
        # Больше не удаляем сообщение об ошибке
        return
    
    # Формируем список участников
    participants_text = f"👥 <b>Участники чата ({len(participants)}):</b>\n\n"
    
    for i, (user_id, username) in enumerate(participants, 1):
        display_name = f"@{username}" if username and not username.startswith("user") else username
        participants_text += f"{i}. {display_name}\n"
    
    participants_text += f"\n💡 Используйте команду /go@имя для метания в конкретного пользователя"
    
    participants_msg = await message.answer(
        participants_text,
        parse_mode="HTML",
        reply_markup=get_throw_button()
    )
    
    logger.info(f"✅ Список участников отправлен пользователю {user.username}")
    
    # Больше не удаляем список участников

@dp.message(F.text.regexp(r"^/participants(?:@[A-Za-z0-9_]+)?(?:\s|$)"))
async def cmd_participants_alias(message: types.Message):
    return await cmd_participants(message)

# Убрали отдельный алиас для /go@user, чтобы избежать двойных срабатываний

async def main():
    """Главная функция"""
    logger.log_startup()
    max_retries = 5
    retry_delay = 10
    
    try:
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
                    retry_delay *= 2
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



