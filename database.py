import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from logger_config import get_logger

logger = get_logger('database')

class Database:
    def __init__(self, db_path: str = "govnomet.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        direct_hits INTEGER DEFAULT 0,
                        misses INTEGER DEFAULT 0,
                        self_hits INTEGER DEFAULT 0,
                        times_hit INTEGER DEFAULT 0,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        -- Новые поля для расширенной механики
                        score INTEGER DEFAULT 0,
                        heat INTEGER DEFAULT 0,
                        last_role TEXT,
                        role_expires_at TIMESTAMP,
                        last_throw_ts TIMESTAMP
                    )
                ''')
                # Альтернативно добавляем недостающие колонки (если таблица уже существовала)
                for col, ddl in [
                    ("score", "ALTER TABLE users ADD COLUMN score INTEGER DEFAULT 0"),
                    ("heat", "ALTER TABLE users ADD COLUMN heat INTEGER DEFAULT 0"),
                    ("last_role", "ALTER TABLE users ADD COLUMN last_role TEXT"),
                    ("role_expires_at", "ALTER TABLE users ADD COLUMN role_expires_at TIMESTAMP"),
                    ("last_throw_ts", "ALTER TABLE users ADD COLUMN last_throw_ts TIMESTAMP"),
                ]:
                    try:
                        cursor.execute(ddl)
                    except Exception:
                        pass
                
                # Таблица событий
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        initiator_id INTEGER,
                        target_id INTEGER,
                        outcome TEXT,
                        chat_id INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        -- Новые поля метаданных события
                        role_used TEXT,
                        stacks_at_hit INTEGER,
                        heat_at_hit INTEGER,
                        was_reflect INTEGER DEFAULT 0,
                        targets_json TEXT,
                        FOREIGN KEY (initiator_id) REFERENCES users (user_id),
                        FOREIGN KEY (target_id) REFERENCES users (user_id)
                    )
                ''')
                # Добавляем недостающие колонки в events, если нужно
                for ddl in [
                    "ALTER TABLE events ADD COLUMN role_used TEXT",
                    "ALTER TABLE events ADD COLUMN stacks_at_hit INTEGER",
                    "ALTER TABLE events ADD COLUMN heat_at_hit INTEGER",
                    "ALTER TABLE events ADD COLUMN was_reflect INTEGER DEFAULT 0",
                    "ALTER TABLE events ADD COLUMN targets_json TEXT",
                ]:
                    try:
                        cursor.execute(ddl)
                    except Exception:
                        pass
                
                # Таблица статистики чатов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_stats (
                        chat_id INTEGER PRIMARY KEY,
                        total_throws INTEGER DEFAULT 0,
                        last_rating_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица ролей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS roles (
                        role_key TEXT PRIMARY KEY,
                        role_name TEXT NOT NULL,
                        emoji TEXT NOT NULL,
                        description TEXT NOT NULL,
                        bonuses TEXT NOT NULL,
                        penalties TEXT,
                        special_effects TEXT,
                        style TEXT NOT NULL
                    )
                ''')
                
                # Таблица фокуса между парами (инициатор -> цель)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS focus_pairs (
                        initiator_id INTEGER,
                        target_id INTEGER,
                        chat_id INTEGER,
                        focus_stacks INTEGER DEFAULT 0,
                        last_hit_ts TIMESTAMP,
                        penalty_until TIMESTAMP,
                        PRIMARY KEY (initiator_id, target_id, chat_id)
                    )
                ''')
                
                conn.commit()
                logger.info("✅ База данных инициализирована успешно")
                
                # Инициализируем роли, если таблица пустая
                self.init_roles()
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
    
    async def add_user(self, user_id: int, username: str = None, 
                      first_name: str = None, last_name: str = None) -> bool:
        """Добавление нового пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name, last_activity)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, username, first_name, last_name))
                conn.commit()
                logger.info(f"👤 Пользователь {user_id} (@{username}) добавлен/обновлен в БД")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя {user_id}: {e}")
            return False
    
    async def update_user_stats(self, user_id: int, outcome: str, is_target: bool = False):
        """Обновление статистики пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if outcome == 'direct_hit':
                    if is_target:
                        cursor.execute('''
                            UPDATE users SET times_hit = times_hit + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"🎯 Пользователь {user_id} получил попадание")
                    else:
                        cursor.execute('''
                            UPDATE users SET direct_hits = direct_hits + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"🎯 Пользователь {user_id} совершил попадание")
                elif outcome == 'miss':
                    if is_target:
                        # Цель получила промах (не должно происходить)
                        logger.debug(f"🤡 Пользователь {user_id} получил промах как цель")
                    else:
                        # Инициатор промахнулся - сам себя обосрал
                        cursor.execute('''
                            UPDATE users SET self_hits = self_hits + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"🤡 Пользователь {user_id} сам себя обосрал")
                elif outcome == 'splash':
                    if is_target:
                        # Цель получила разлёт
                        cursor.execute('''
                            UPDATE users SET times_hit = times_hit + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"💥 Пользователь {user_id} получил разлёт")
                    else:
                        # Инициатор совершил разлёт
                        cursor.execute('''
                            UPDATE users SET direct_hits = direct_hits + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"💥 Пользователь {user_id} совершил разлёт")
                elif outcome == 'special':
                    if is_target:
                        # Цель получила особый эффект
                        cursor.execute('''
                            UPDATE users SET times_hit = times_hit + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"⚡ Пользователь {user_id} получил особый эффект")
                    else:
                        # Инициатор попал под особый эффект (бумеранг и т.д.)
                        cursor.execute('''
                            UPDATE users SET self_hits = self_hits + 1 
                            WHERE user_id = ?
                        ''', (user_id,))
                        logger.debug(f"⚡ Пользователь {user_id} попал под особый эффект")
                
                cursor.execute('''
                    UPDATE users SET last_activity = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (user_id,))
                
                conn.commit()
                logger.debug(f"📊 Статистика пользователя {user_id} обновлена: {outcome}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики пользователя {user_id}: {e}")
    
    async def add_event(self, initiator_id: int, target_id: int, 
                       outcome: str, chat_id: int,
                       role_used: str = None,
                       stacks_at_hit: int = None,
                       heat_at_hit: int = None,
                       was_reflect: int = 0,
                       targets_json: str = None) -> bool:
        """Добавление события броска"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO events (initiator_id, target_id, outcome, chat_id, role_used, stacks_at_hit, heat_at_hit, was_reflect, targets_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (initiator_id, target_id, outcome, chat_id, role_used, stacks_at_hit, heat_at_hit, was_reflect, targets_json))
                
                # Обновляем статистику чата
                cursor.execute('''
                    INSERT OR REPLACE INTO chat_stats (chat_id, total_throws)
                    VALUES (?, COALESCE((SELECT total_throws FROM chat_stats WHERE chat_id = ?), 0) + 1)
                ''', (chat_id, chat_id))
                
                # Обновляем статистику пользователя-инициатора
                if outcome == 'direct_hit':
                    cursor.execute('''
                        UPDATE users SET direct_hits = COALESCE(direct_hits, 0) + 1 
                        WHERE user_id = ?
                    ''', (initiator_id,))
                elif outcome == 'miss':
                    cursor.execute('''
                        UPDATE users SET misses = COALESCE(misses, 0) + 1, 
                                       self_hits = COALESCE(self_hits, 0) + 1
                        WHERE user_id = ?
                    ''', (initiator_id,))
                elif outcome == 'special':
                    # Проверяем, попал ли инициатор в себя (например, бумеранг)
                    if targets_json and str(initiator_id) in targets_json:
                        cursor.execute('''
                            UPDATE users SET self_hits = COALESCE(self_hits, 0) + 1 
                            WHERE user_id = ?
                        ''', (initiator_id,))
                
                # Обновляем статистику цели
                if outcome == 'direct_hit':
                    cursor.execute('''
                        UPDATE users SET times_hit = COALESCE(times_hit, 0) + 1 
                        WHERE user_id = ?
                    ''', (target_id,))
                
                conn.commit()
                logger.info(f"💩 Событие добавлено: {initiator_id} -> {target_id} ({outcome}) в чате {chat_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления события: {e}")
            return False

    # ---------------------- Расширенные операции ----------------------
    async def get_user_extended(self, user_id: int) -> Optional[tuple]:
        """Возвращает (score, heat, last_role, role_expires_at, last_throw_ts)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT score, heat, last_role, role_expires_at, last_throw_ts
                    FROM users WHERE user_id = ?
                ''', (user_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Ошибка получения расширенных данных пользователя {user_id}: {e}")
            return None

    async def update_user_heat(self, user_id: int, delta: int = 1):
        """Увеличивает heat (с зажимом 0..100)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET heat = MAX(0, MIN(100, COALESCE(heat, 0) + ?)), last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (delta, user_id))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления heat пользователя {user_id}: {e}")

    async def update_user_role(self, user_id: int, role: str, expires_at: Optional[str]):
        """Сохраняет выбранную роль и срок её действия."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET last_role = ?, role_expires_at = ?, last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (role, expires_at, user_id))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления роли пользователя {user_id}: {e}")

    async def update_user_last_throw(self, user_id: int):
        """Фиксирует время последнего броска."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET last_throw_ts = CURRENT_TIMESTAMP, last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (user_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка фиксации последнего броска пользователя {user_id}: {e}")

    async def update_score(self, user_id: int, delta: int):
        """Изменяет общий счёт игрока."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET score = COALESCE(score, 0) + ?, last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (delta, user_id))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления счёта пользователя {user_id}: {e}")

    async def get_focus(self, initiator_id: int, target_id: int, chat_id: int) -> Tuple[int, Optional[str], Optional[str]]:
        """Возвращает (focus_stacks, last_hit_ts, penalty_until)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT focus_stacks, last_hit_ts, penalty_until
                    FROM focus_pairs WHERE initiator_id = ? AND target_id = ? AND chat_id = ?
                ''', (initiator_id, target_id, chat_id))
                row = cursor.fetchone()
                if row:
                    return row[0], row[1], row[2]
                return 0, None, None
        except Exception as e:
            logger.error(f"❌ Ошибка получения фокуса пары {initiator_id}->{target_id} чата {chat_id}: {e}")
            return 0, None, None

    async def set_focus(self, initiator_id: int, target_id: int, chat_id: int, stacks: int, penalty_until: Optional[str] = None):
        """Сохраняет focus_stacks и временные штрафы для пары инициатор→цель."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO focus_pairs (initiator_id, target_id, chat_id, focus_stacks, last_hit_ts, penalty_until)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(initiator_id, target_id, chat_id)
                    DO UPDATE SET focus_stacks=excluded.focus_stacks, last_hit_ts=CURRENT_TIMESTAMP, penalty_until=excluded.penalty_until
                ''', (initiator_id, target_id, chat_id, stacks, penalty_until))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения фокуса пары {initiator_id}->{target_id}: {e}")
    
    async def get_chat_participants(self, chat_id: int) -> List[Tuple[int, str]]:
        """Получение списка участников чата (заглушка - в реальности нужно получать через Telegram API)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT u.user_id, u.username 
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id OR u.user_id = e.target_id
                    WHERE e.chat_id = ?
                    ORDER BY u.last_activity DESC
                ''', (chat_id,))
                participants = cursor.fetchall()
                logger.debug(f"👥 Получено {len(participants)} участников чата {chat_id}")
                return participants
        except Exception as e:
            logger.error(f"❌ Ошибка получения участников чата {chat_id}: {e}")
            return []
    
    async def get_ratings(self, chat_id: int, days: int = 7) -> dict:
        """Получение рейтингов за указанный период"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                since_date = datetime.now() - timedelta(days=days)
                since_str = since_date.isoformat()
                
                # Король говна (больше всего попаданий)
                cursor.execute('''
                    SELECT u.username, COUNT(*) as hits
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.outcome = 'direct_hit'
                      AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY hits DESC
                    LIMIT 1
                ''', (chat_id, since_str))
                king = cursor.fetchone()
                
                # Главный обосранный (чаще всего страдал)
                cursor.execute('''
                    SELECT u.username, COUNT(*) as hit_count
                    FROM users u
                    JOIN events e ON u.user_id = e.target_id
                    WHERE e.chat_id = ? AND e.outcome = 'direct_hit'
                      AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY hit_count DESC
                    LIMIT 1
                ''', (chat_id, since_str))
                victim = cursor.fetchone()
                
                # Долбоёб недели (чаще всех сам себя обосрал)
                cursor.execute('''
                    SELECT u.username,
                           SUM(CASE WHEN e.outcome = 'miss' THEN 1 ELSE 0 END)
                         + SUM(CASE WHEN e.outcome = 'special' AND e.targets_json LIKE '%' || u.user_id || '%' THEN 1 ELSE 0 END) AS self_count
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    HAVING self_count > 0
                    ORDER BY self_count DESC
                    LIMIT 1
                ''', (chat_id, since_str))
                idiot = cursor.fetchone()
                
                logger.info(f"🏆 Рейтинги для чата {chat_id} за {days} дней получены")
                return {
                    'king': king,
                    'victim': victim,
                    'idiot': idiot
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения рейтингов для чата {chat_id}: {e}")
            return {}
    
    async def get_user_stats(self, user_id: int, chat_id: int) -> dict:
        """Получение статистики конкретного пользователя в конкретном чате"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем статистику из событий по чату
                cursor.execute('''
                    SELECT 
                        SUM(CASE WHEN outcome = 'direct_hit' AND initiator_id = ? THEN 1 ELSE 0 END) as direct_hits,
                        SUM(CASE WHEN outcome = 'splash' AND initiator_id = ? THEN 1 ELSE 0 END) as splash_hits,
                        SUM(CASE WHEN outcome = 'miss' AND initiator_id = ? THEN 1 ELSE 0 END) as self_hits,
                        SUM(CASE WHEN (outcome = 'direct_hit' OR outcome = 'splash' OR outcome = 'special') AND target_id = ? THEN 1 ELSE 0 END) as times_hit
                    FROM events 
                    WHERE chat_id = ? AND (initiator_id = ? OR target_id = ?)
                ''', (user_id, user_id, user_id, user_id, chat_id, user_id, user_id))
                
                result = cursor.fetchone()
                
                if result:
                    stats = {
                        'direct_hits': result[0] or 0,
                        'misses': 0,  # misses теперь считаются как self_hits
                        'self_hits': result[2] or 0,
                        'times_hit': result[3] or 0
                    }
                    logger.debug(f"📊 Статистика пользователя {user_id} в чате {chat_id}: {stats}")
                    return stats
                logger.warning(f"⚠️ Пользователь {user_id} не найден в чате {chat_id}")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователя {user_id} в чате {chat_id}: {e}")
            return {}
    
    async def get_chat_stats(self, chat_id: int, days: int = 30) -> dict:
        """Получение общей статистики чата"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                since_date = datetime.now() - timedelta(days=days)
                
                # Общее количество бросков
                cursor.execute('''
                    SELECT COUNT(*) as total_throws
                    FROM events WHERE chat_id = ? AND timestamp >= ?
                ''', (chat_id, since_date))
                total_throws = cursor.fetchone()[0]
                
                # Статистика по исходам
                cursor.execute('''
                    SELECT outcome, COUNT(*) as count
                    FROM events WHERE chat_id = ? AND timestamp >= ?
                    GROUP BY outcome
                ''', (chat_id, since_date))
                outcomes = dict(cursor.fetchall())
                
                # Топ метателей
                cursor.execute('''
                    SELECT u.username, COUNT(*) as throws
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY throws DESC
                    LIMIT 3
                ''', (chat_id, since_date))
                top_throwers = cursor.fetchall()
                
                # Топ страдальцев
                cursor.execute('''
                    SELECT u.username, COUNT(*) as hits
                    FROM users u
                    JOIN events e ON u.user_id = e.target_id
                    WHERE e.chat_id = ? AND e.outcome = 'direct_hit' AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY hits DESC
                    LIMIT 3
                ''', (chat_id, since_date))
                top_victims = cursor.fetchall()
                
                # Топ неудачников (сам себя обосрал)
                cursor.execute('''
                    SELECT u.username, u.self_hits
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    HAVING u.self_hits > 0
                    ORDER BY u.self_hits DESC
                    LIMIT 3
                ''', (chat_id, since_date))
                top_losers = cursor.fetchall()
                
                # Топ снайперов (лучший процент попаданий)
                cursor.execute('''
                    SELECT u.username, 
                           COUNT(CASE WHEN e.outcome IN ('direct_hit', 'critical') THEN 1 END) as direct_hits,
                           COUNT(*) as total_throws,
                           CASE 
                               WHEN COUNT(*) > 0 
                               THEN ROUND(COUNT(CASE WHEN e.outcome IN ('direct_hit', 'critical') THEN 1 END) * 100.0 / COUNT(*), 1)
                               ELSE 0 
                           END as accuracy
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    HAVING COUNT(*) >= 5
                    ORDER BY accuracy DESC
                    LIMIT 3
                ''', (chat_id, since_date))
                top_snipers = cursor.fetchall()
                
                # Самый активный день
                cursor.execute('''
                    SELECT DATE(timestamp) as date, COUNT(*) as throws
                    FROM events 
                    WHERE chat_id = ? AND timestamp >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY throws DESC
                    LIMIT 1
                ''', (chat_id, since_date))
                most_active_day = cursor.fetchone()
                
                logger.info(f"📊 Общая статистика чата {chat_id} за {days} дней получена")
                return {
                    'total_throws': total_throws,
                    'outcomes': outcomes,
                    'top_throwers': top_throwers,
                    'top_victims': top_victims,
                    'top_losers': top_losers,
                    'top_snipers': top_snipers,
                    'most_active_day': most_active_day
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения общей статистики чата {chat_id}: {e}")
            return {}
    
    async def get_game_stats(self, chat_id: int, days: int = 30) -> dict:
        """Получение игровой статистики"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                since_date = datetime.now() - timedelta(days=days)
                
                # Самый длинный говно-стрик (серия успешных бросков)
                cursor.execute('''
                    SELECT u.username, 
                           (SELECT COUNT(*) FROM (
                               SELECT e1.outcome, 
                                      ROW_NUMBER() OVER (ORDER BY e1.timestamp) as rn
                               FROM events e1 
                               WHERE e1.initiator_id = u.user_id 
                               AND e1.chat_id = ? 
                               AND e1.timestamp >= ?
                               ORDER BY e1.timestamp
                           ) t WHERE t.outcome IN ('direct_hit', 'critical', 'combo'))
                           as streak
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY streak DESC
                    LIMIT 1
                ''', (chat_id, since_date, chat_id, since_date))
                longest_streak = cursor.fetchone()
                
                # Говно-мастер (метнул во всех участников)
                cursor.execute('''
                    SELECT u.username, COUNT(DISTINCT e.target_id) as unique_targets
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY unique_targets DESC
                    LIMIT 1
                ''', (chat_id, since_date))
                shit_master = cursor.fetchone()
                
                # Говно-везение (кто чаще всего избегал попаданий)
                cursor.execute('''
                    SELECT u.username, 
                           (SELECT COUNT(*) FROM events e2 
                            WHERE e2.target_id = u.user_id 
                            AND e2.chat_id = ? 
                            AND e2.timestamp >= ?) as times_hit,
                           (SELECT COUNT(*) FROM events e3 
                            WHERE e3.initiator_id = u.user_id 
                            AND e3.chat_id = ? 
                            AND e3.timestamp >= ?) as times_thrown
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id OR u.user_id = e.target_id
                    WHERE e.chat_id = ? AND e.timestamp >= ?
                    GROUP BY u.user_id
                    HAVING times_thrown >= 3
                    ORDER BY (times_thrown - times_hit) DESC
                    LIMIT 1
                ''', (chat_id, since_date, chat_id, since_date, chat_id, since_date))
                lucky_bastard = cursor.fetchone()
                
                # Говно-маг (чаще всего особые эффекты)
                cursor.execute('''
                    SELECT u.username, COUNT(*) as special_effects
                    FROM users u
                    JOIN events e ON u.user_id = e.initiator_id
                    WHERE e.chat_id = ? AND e.outcome = 'special' AND e.timestamp >= ?
                    GROUP BY u.user_id
                    ORDER BY special_effects DESC
                    LIMIT 1
                ''', (chat_id, since_date))
                shit_mage = cursor.fetchone()
                
                logger.info(f"🎮 Игровая статистика чата {chat_id} за {days} дней получена")
                return {
                    'longest_streak': longest_streak,
                    'shit_master': shit_master,
                    'lucky_bastard': lucky_bastard,
                    'shit_mage': shit_mage
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения игровой статистики чата {chat_id}: {e}")
            return {}
    
    def init_roles(self):
        """Инициализация ролей в базе данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, есть ли уже роли в БД
                cursor.execute("SELECT COUNT(*) FROM roles")
                count = cursor.fetchone()[0]
                
                if count > 0:
                    logger.info("🎭 Роли уже инициализированы в БД")
                    return
                
                # Данные всех ролей
                roles_data = [
                    # Базовые роли
                    ('sniper', '🎯 Снайпер', '🎯', 'Мастер точности', 
                     '+50% к прямому попаданию, -30% к разлёту', None, None, 'Точечные удары, минимальный урон по невиновным'),
                    
                    ('bombardier', '💣 Бомбардир', '💣', 'Массовое поражение',
                     '+80% к разлёту, -20% к точности', None, None, 'Хаотичные взрывы, много жертв одновременно'),
                    
                    ('defender', '🛡️ Оборонец', '🛡️', 'Защитник',
                     'Повышенный шанс отражения атак', None, None, 'Защитная тактика, отбивает атаки обратно'),
                    
                    # Обидные роли
                    ('drunk_sniper', '🍺🎯 Снайпер-пьяница', '🍺🎯', 'Точность с риском',
                     '+30% к точности в обычном состоянии', 'При жаре ≥50 шанс промаха удваивается', 'Чем больше агрессии, тем хуже прицел', 'Точность с риском'),
                    
                    ('berserker', '🪓 Берсерк', '🪓', 'Ярость и мощь',
                     '+60% к критическим ударам, +50% к комбо', 'Каждый бросок +5 к жару, штраф к промаху не уменьшается', None, 'Агрессивная атака без пощады'),
                    
                    ('trickster', '🃏 Трикстер', '🃏', 'Мастер обмана',
                     '+40% к особым эффектам', None, '10% шанс превратить попадание в "бумеранг" по метателю', 'Непредсказуемые трюки и розыгрыши'),
                    
                    # Тактические роли
                    ('magnet', '🧲 Магнит', '🧲', 'Фокус-мастер',
                     'Первый удар по цели даёт +1 к фокусу мгновенно', None, 'При фокусе >2 шанс прямого попадания ↑', 'Концентрированная атака на одну цель'),
                    
                    ('saboteur', '🕳️ Саботажник', '🕳️', 'Подрывник',
                     'Снижает точность цели в ответ', '+30% к промаху цели на 10 минут', 'Психологическая война', 'Подрывная деятельность'),
                    
                    ('oracle', '🔮 Оракул', '🔮', 'Предсказатель',
                     'Кулдаун -40% (быстрее бросает)', 'Вес "legendary" урезан в 2 раза', 'Умеет тащить "brick" вместо "miss"', 'Частые, но менее мощные атаки'),
                    
                    # Огненные роли
                    ('pyromaniac', '🔥 Пироман', '🔥', 'Мастер огня',
                     'Жар растёт вдвое быстрее', None, 'При жаре ≥20 получает +50% к криту, при жаре ≥80 шанс "special: bomb/rain"↑', 'Эскалация агрессии до взрыва'),
                    
                    ('shieldbearer', '🛡️ Щитоносец', '🛡️', 'Непробиваемый',
                     'Шанс авто-рефлекта малых ударов', None, 'Фокус по нему накапливается медленнее', 'Оборонительная тактика с контратаками'),
                    
                    # Специализированные роли
                    ('collector', '📎 Коллектор', '📎', 'Охотник за целями',
                     '+40% к точности по тем, по кому уже есть фокус', 'Против свежих целей обычная точность', None, 'Добивание уже раненых целей'),
                    
                    ('teleporter', '🌀 Телепортер', '🌀', 'Перекидыватель',
                     '15% шанс перекинуть цель на рандомного участника', None, 'Цель "телепортируется" к другому игроку', 'Хаотичные перенаправления'),
                    
                    ('rocketeer', '🚀 Говноракетчик', '🚀', 'Ракетный удар',
                     '+30% к разлёту, +20% к особым эффектам', '-10% к точности', None, 'Мощные, но неточные залпы'),
                    
                    # Грязные роли
                    ('snot_sniper', '🤧 Сопля-снайпер', '🤧', 'Слизистый стрелок',
                     '+10% к промаху', '20% шанс удвоить промах', 'Случайные "сопливые" промахи', 'Непредсказуемая точность'),
                    
                    ('acid_clown', '🧪🤡 Кислотный клоун', '🧪🤡', 'Химический террор',
                     'Особые химические эффекты', None, 'Токсичные розыгрыши и химические атаки', 'Химическая война'),
                    
                    ('counter_guru', '🔁 Обратка-гуру', '🔁', 'Мастер контратак',
                     'Специализация на ответных ударах', None, 'Контратаки и ответные удары', 'Мастерство контратак')
                ]
                
                # Вставляем роли в БД
                cursor.executemany('''
                    INSERT INTO roles (role_key, role_name, emoji, description, bonuses, penalties, special_effects, style)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', roles_data)
                
                conn.commit()
                logger.info(f"🎭 Инициализировано {len(roles_data)} ролей в БД")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации ролей: {e}")
    
    async def get_role_info(self, role_key: str) -> Optional[dict]:
        """Получение информации о роли"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT role_key, role_name, emoji, description, bonuses, penalties, special_effects, style
                    FROM roles WHERE role_key = ?
                ''', (role_key,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'role_key': result[0],
                        'role_name': result[1],
                        'emoji': result[2],
                        'description': result[3],
                        'bonuses': result[4],
                        'penalties': result[5],
                        'special_effects': result[6],
                        'style': result[7]
                    }
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о роли {role_key}: {e}")
            return None
