import random
import asyncio
from typing import List, Tuple, Dict, Optional, Any
from datetime import datetime, timedelta
from config import OUTCOME_PROBABILITIES, GAME_MESSAGES
from logger_config import get_logger

logger = get_logger('game')

# Константы для новой механики
ROLE_DURATION = 3600  # 1 час в секундах
MIN_THROW_INTERVAL = 30  # Минимальный интервал между бросками
FOCUS_PENALTY_DURATION = 300  # 5 минут штрафа за фокус

class GameLogic:
    def __init__(self):
        self.outcomes = list(OUTCOME_PROBABILITIES.keys())
        self.weights = list(OUTCOME_PROBABILITIES.values())
        self.combo_counters = {}  # Счетчики комбо для каждого пользователя
        self.streak_counters = {}  # Счетчики серий для каждого пользователя
        # Новые поля для расширенной механики
        self.user_roles = {}  # user_id -> (role, expires_at)
        self.user_heat = {}   # user_id -> heat (0-100)
        self.user_scores = {} # user_id -> score
        self.focus_stacks = {} # (initiator_id, target_id, chat_id) -> stacks
        self.last_throws = {} # user_id -> timestamp
        self.cooldowns = {}   # (initiator_id, target_id, chat_id) -> penalty_until
        logger.info("🎮 Игровая логика ГовноМёт инициализирована")
    
    # ---------------------- Новая механика: роли и модификаторы ----------------------
    def assign_random_role(self, user_id: int) -> str:
        """Назначает случайную роль пользователю на 1 час"""
        roles = ['sniper', 'bombardier', 'defender']
        role = random.choice(roles)
        expires_at = datetime.now() + timedelta(seconds=ROLE_DURATION)
        self.user_roles[user_id] = (role, expires_at)
        logger.info(f"🎭 Пользователю {user_id} назначена роль {role} до {expires_at}")
        return role
    
    def get_user_role(self, user_id: int) -> Optional[str]:
        """Возвращает активную роль пользователя или None"""
        if user_id not in self.user_roles:
            return None
        
        role, expires_at = self.user_roles[user_id]
        if datetime.now() > expires_at:
            del self.user_roles[user_id]
            return None
        
        return role
    
    def apply_role_modifiers(self, base_weights: List[float], role: str) -> List[float]:
        """Применяет модификаторы роли к базовым весам исхода"""
        modified_weights = base_weights.copy()
        
        if role == 'sniper':
            # Снайпер: +точность, -разлет
            modified_weights[0] *= 1.5  # direct_hit
            modified_weights[2] *= 0.7  # splash
            logger.debug(f"🎯 Модификатор снайпера применен: точность↑, разлет↓")
        
        elif role == 'bombardier':
            # Бомбардир: +разлет, -точность
            modified_weights[0] *= 0.8  # direct_hit
            modified_weights[2] *= 1.8  # splash
            logger.debug(f"💣 Модификатор бомбардира применен: разлет↑, точность↓")
        
        elif role == 'defender':
            # Оборонец: +шанс отражения
            # Это будет применено в логике исхода
            logger.debug(f"🛡️ Модификатор оборонца применен: отражение↑")
        
        return modified_weights
    
    def calculate_focus_penalty(self, initiator_id: int, target_id: int, chat_id: int) -> float:
        """Рассчитывает штраф за фокус на одну цель"""
        key = (initiator_id, target_id, chat_id)
        stacks = self.focus_stacks.get(key, 0)
        
        if stacks == 0:
            return 1.0
        
        # Каждый повторный удар по одной цели увеличивает штраф
        penalty = 1.0 + (stacks * 0.3)  # +30% за каждый удар
        logger.debug(f"🎯 Штраф за фокус {initiator_id}->{target_id}: {penalty:.2f}x (stacks: {stacks})")
        return penalty
    
    def calculate_heat_bonus(self, user_id: int) -> float:
        """Рассчитывает бонус/штраф за репутацию агрессора"""
        heat = self.user_heat.get(user_id, 0)
        
        if heat <= 20:
            return 1.0  # Нейтральная репутация
        elif heat <= 50:
            return 1.2  # Легкий бонус
        elif heat <= 80:
            return 1.5  # Средний бонус
        else:
            return 2.0  # Высокий бонус (но и высокий риск)
    
    def calculate_comeback_bonus(self, user_id: int, chat_id: int) -> float:
        """Рассчитывает бонус камбэка для отстающих игроков"""
        # TODO: Реализовать через БД - получить средний счёт в чате
        # Пока возвращаем базовый множитель
        return 1.0
    
    def check_cooldown(self, user_id: int) -> bool:
        """Проверяет, не находится ли пользователь в кулдауне"""
        if user_id not in self.last_throws:
            return False
        
        last_throw = self.last_throws[user_id]
        time_since = (datetime.now() - last_throw).total_seconds()
        
        if time_since < MIN_THROW_INTERVAL:
            logger.debug(f"⏰ Пользователь {user_id} в кулдауне: {MIN_THROW_INTERVAL - time_since:.1f}s осталось")
            return True
        
        return False
    
    def update_focus_stacks(self, initiator_id: int, target_id: int, chat_id: int):
        """Обновляет счётчик фокуса на цель"""
        key = (initiator_id, target_id, chat_id)
        self.focus_stacks[key] = self.focus_stacks.get(key, 0) + 1
        logger.debug(f"🎯 Фокус {initiator_id}->{target_id}: {self.focus_stacks[key]} stacks")
    
    def update_user_heat(self, user_id: int, delta: int = 1):
        """Обновляет heat пользователя (0-100)"""
        current_heat = self.user_heat.get(user_id, 0)
        new_heat = max(0, min(100, current_heat + delta))
        self.user_heat[user_id] = new_heat
        logger.debug(f"🔥 Heat пользователя {user_id}: {current_heat} -> {new_heat}")
    
    def update_user_score(self, user_id: int, delta: int):
        """Обновляет счёт пользователя"""
        current_score = self.user_scores.get(user_id, 0)
        self.user_scores[user_id] = current_score + delta
        logger.debug(f"📊 Счёт пользователя {user_id}: {current_score} -> {self.user_scores[user_id]}")
    
    def record_throw(self, user_id: int):
        """Записывает время последнего броска пользователя"""
        self.last_throws[user_id] = datetime.now()
    
    # ---------------------- Обновлённая логика исхода ----------------------
    def determine_outcome(self, user_id: int = None) -> str:
        """Определение исхода броска на основе вероятностей и комбо"""
        # Базовые вероятности
        base_weights = self.weights.copy()
        
        # Если есть пользователь, применяем бонусы за комбо и серии
        if user_id is not None:
            # Применяем модификаторы роли
            role = self.get_user_role(user_id)
            if role:
                base_weights = self.apply_role_modifiers(base_weights, role)
            
            combo_count = self.combo_counters.get(user_id, 0)
            streak_count = self.streak_counters.get(user_id, 0)
            
            # Бонус за комбо
            if combo_count >= 5:
                # Увеличиваем шанс на critical и combo
                base_weights[4] *= 2  # critical
                base_weights[5] *= 3   # combo
                logger.debug(f"🔄 Бонус комбо x{combo_count} применен для пользователя {user_id}")
            
            # Бонус за серию
            if streak_count >= 10:
                # Увеличиваем шанс на legendary
                base_weights[6] *= 4   # legendary
                logger.debug(f"🔥 Бонус серии x{streak_count} применен для пользователя {user_id}")
        
        # Нормализуем веса
        total_weight = sum(base_weights)
        base_weights = [w / total_weight for w in base_weights]
        
        outcome = random.choices(self.outcomes, weights=base_weights, k=1)[0]
        logger.debug(f"🎲 Определен исход броска: {outcome}")
        return outcome
    
    def get_random_message(self, outcome: str, **kwargs) -> str:
        """Получение случайного сообщения для исхода"""
        if outcome not in GAME_MESSAGES:
            logger.warning(f"⚠️ Неизвестный исход: {outcome}")
            return "Что-то пошло не так... 💩"
        
        messages = GAME_MESSAGES[outcome]
        message = random.choice(messages)
        
        # Заменяем плейсхолдеры
        formatted_message = message.format(**kwargs)
        logger.debug(f"💬 Выбрано сообщение для исхода {outcome}: {formatted_message}")
        return formatted_message
    
    def select_targets(self, participants: List[Tuple[int, str]], 
                      initiator_id: int, outcome: str) -> List[Tuple[int, str]]:
        """Выбор целей в зависимости от исхода"""
        if not participants:
            logger.warning("⚠️ Список участников пуст")
            return []
        
        # Убираем инициатора из списка возможных целей
        available_targets = [p for p in participants if p[0] != initiator_id]
        
        if not available_targets:
            # Если инициатор единственный участник, он становится целью
            logger.info(f"🎯 Инициатор {initiator_id} - единственный участник, становится целью")
            return [participants[0]]
        
        if outcome == 'direct_hit':
            # Прямое попадание - одна случайная цель
            target = random.choice(available_targets)
            logger.debug(f"🎯 Прямое попадание: выбрана цель {target[1]} (ID: {target[0]})")
            return [target]
        
        elif outcome == 'miss':
            # Промах - инициатор сам себя обосрал
            initiator = next((p for p in participants if p[0] == initiator_id), None)
            if initiator:
                logger.debug(f"🤡 Промах: инициатор {initiator[1]} (ID: {initiator[0]}) сам себя обосрал")
                return [initiator]
            else:
                logger.warning(f"⚠️ Инициатор {initiator_id} не найден в списке участников")
                return available_targets[:1]
        
        elif outcome == 'splash':
            # Разлетелось - несколько случайных целей (2-4)
            num_targets = min(random.randint(2, 4), len(available_targets))
            targets = random.sample(available_targets, num_targets)
            target_names = [t[1] for t in targets]
            logger.debug(f"🤮 Разлетелось: выбрано {num_targets} целей: {target_names}")
            return targets
        
        elif outcome == 'special':
            # Особые эффекты
            effect_type = random.choice(['boomerang', 'avalanche', 'brick', 'bomb', 'rain', 'lightning', 'fire', 'ice', 'rainbow', 'theater', 'circus', 'art', 'music', 'movie', 'game'])
            logger.debug(f"⚡ Особый эффект: {effect_type}")
            
            if effect_type == 'boomerang':
                # Бумеранг - инициатор сам себя обосрал
                initiator = next((p for p in participants if p[0] == initiator_id), None)
                if initiator:
                    logger.debug(f"🔄 Бумеранг: инициатор {initiator[1]} (ID: {initiator[0]}) сам себя обосрал")
                    return [initiator]
                else:
                    return available_targets[:1]
            
            elif effect_type == 'avalanche':
                # Лавина - весь чат
                logger.debug(f"🌪️ Лавина: весь чат ({len(available_targets)} участников) обосран")
                return available_targets
            
            elif effect_type == 'brick':
                # Кирпич - случайная цель
                target = random.choice(available_targets)
                logger.debug(f"🧱 Кирпич: выбрана цель {target[1]} (ID: {target[0]})")
                return [target]
            
            elif effect_type == 'bomb':
                # Говнобомба - несколько случайных целей
                num_targets = min(random.randint(3, 5), len(available_targets))
                targets = random.sample(available_targets, num_targets)
                target_names = [t[1] for t in targets]
                logger.debug(f"💣 Говнобомба: выбрано {num_targets} целей: {target_names}")
                return targets
            
            elif effect_type == 'rain':
                # Говнодождь - весь чат
                logger.debug(f"🌧️ Говнодождь: весь чат ({len(available_targets)} участников) обосран")
                return available_targets
            
            elif effect_type in ['lightning', 'fire', 'ice', 'rainbow', 'theater', 'circus', 'art', 'music', 'movie', 'game']:
                # Остальные особые эффекты - случайная цель
                target = random.choice(available_targets)
                logger.debug(f"🎭 Особый эффект {effect_type}: выбрана цель {target[1]} (ID: {target[0]})")
                return [target]
        
        elif outcome == 'critical':
            # Критическое попадание - одна цель с максимальным уроном
            target = random.choice(available_targets)
            logger.debug(f"💥 Критическое попадание: выбрана цель {target[1]} (ID: {target[0]})")
            return [target]
        
        elif outcome == 'combo':
            # Комбо-эффект - несколько целей (3-5)
            num_targets = min(random.randint(3, 5), len(available_targets))
            targets = random.sample(available_targets, num_targets)
            target_names = [t[1] for t in targets]
            logger.debug(f"🔄 Комбо: выбрано {num_targets} целей: {target_names}")
            return targets
        
        elif outcome == 'legendary':
            # Легендарный исход - весь чат
            logger.debug(f"👑 Легендарный исход: весь чат ({len(available_targets)} участников) обосран")
            return available_targets
        
        logger.debug(f"🎯 Возвращаем одну случайную цель")
        return available_targets[:1]
    
    def format_targets_text(self, targets: List[Tuple[int, str]]) -> str:
        """Форматирование списка целей в текст"""
        if not targets:
            logger.debug("📝 Форматирование целей: список пуст")
            return "никого"
        
        usernames = [f"@{target[1]}" if target[1] else f"user{target[0]}" for target in targets]
        
        if len(usernames) == 1:
            result = usernames[0]
        elif len(usernames) == 2:
            result = f"{usernames[0]} и {usernames[1]}"
        else:
            result = f"{', '.join(usernames[:-1])} и {usernames[-1]}"
        
        logger.debug(f"📝 Форматирование целей: {result}")
        return result
    
    def process_throw(self, initiator_id: int, initiator_username: str,
                     participants: List[Tuple[int, str]], chat_id: int) -> Dict:
        """Обработка броска говна"""
        try:
            logger.info(f"💩 Обработка броска: {initiator_username} (ID: {initiator_id}) в чате {chat_id}")
            logger.debug(f"👥 Участники чата: {len(participants)}")
            
            # Проверяем кулдаун
            if self.check_cooldown(initiator_id):
                return {
                    'outcome': 'cooldown',
                    'message': f"⏰ {initiator_username}, подожди ещё немного перед следующим броском!",
                    'targets': [(initiator_id, initiator_username)],
                    'initiator_id': initiator_id,
                    'chat_id': chat_id,
                    'error': 'cooldown'
                }
            
            # Назначаем роль, если её нет
            if not self.get_user_role(initiator_id):
                role = self.assign_random_role(initiator_id)
                logger.info(f"🎭 Пользователю {initiator_username} назначена роль: {role}")
            
            # Обновляем время последнего броска
            self.record_throw(initiator_id)
            
            # Определяем исход
            outcome = self.determine_outcome(initiator_id)
            
            # Выбираем цели
            targets = self.select_targets(participants, initiator_id, outcome)
            
            # Обновляем счетчики комбо и серий
            combo_count = self.update_combo_counter(initiator_id, outcome)
            streak_count = self.update_streak_counter(initiator_id, outcome)
            
            # Обновляем heat и счёт
            self.update_user_heat(initiator_id, 2)  # +2 heat за бросок
            score_delta = 0
            if outcome == 'direct_hit':
                score_delta = 10
            elif outcome == 'miss':
                score_delta = -5
            self.update_user_score(initiator_id, score_delta)
            
            # Получаем текущую роль для публичных сигналов
            current_role = self.get_user_role(initiator_id)
            
            # Формируем сообщение
            if outcome == 'direct_hit':
                target = targets[0]
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               target=target[1] if target[1] else f"user{target[0]}")
            
            elif outcome == 'miss':
                message = self.get_random_message(outcome, initiator=initiator_username)
            
            elif outcome == 'splash':
                targets_text = self.format_targets_text(targets)
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               targets=targets_text)
            
            elif outcome == 'special':
                if len(targets) == 1 and targets[0][0] == initiator_id:
                    # Бумеранг или сам себя обосрал
                    message = self.get_random_message(outcome, initiator=initiator_username)
                else:
                    targets_text = self.format_targets_text(targets)
                    message = self.get_random_message(outcome, 
                                                   initiator=initiator_username,
                                                   targets=targets_text)
            
            elif outcome == 'critical':
                target = targets[0]
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               target=target[1] if target[1] else f"user{target[0]}")
            
            elif outcome == 'combo':
                targets_text = self.format_targets_text(targets)
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               targets=targets_text)
            
            elif outcome == 'legendary':
                targets_text = self.format_targets_text(targets)
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               targets=targets_text)
            
            result = {
                'outcome': outcome,
                'message': message,
                'targets': targets,
                'initiator_id': initiator_id,
                'chat_id': chat_id,
                'combo_count': combo_count,
                'streak_count': streak_count,
                'combo_bonus': self.get_combo_bonus(combo_count),
                'streak_bonus': self.get_streak_bonus(streak_count),
                # Новые поля для расширенной механики
                'role_used': current_role,
                'heat_at_throw': self.user_heat.get(initiator_id, 0),
                'focus_stacks': 0,  # Будет обновлено в bot.py
                'score_delta': score_delta,
                'public_signals': self.generate_public_signals(initiator_id, targets, chat_id, current_role)
            }
            
            logger.info(f"✅ Бросок обработан: {outcome} -> {len(targets)} целей")
            logger.debug(f"📊 Результат: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки броска: {e}")
            return {
                'outcome': 'miss',
                'message': f"{initiator_username} что-то пошло не так и он обосрался сам 💩",
                'targets': [(initiator_id, initiator_username)],
                'initiator_id': initiator_id,
                'chat_id': chat_id
            }
    
    def process_throw_at_target(self, initiator_id: int, initiator_username: str,
                               target_id: int, target_username: str, chat_id: int) -> Dict:
        """Обработка броска говна в конкретную цель"""
        try:
            logger.info(f"💩 Целевой бросок: {initiator_username} (ID: {initiator_id}) -> {target_username} (ID: {target_id}) в чате {chat_id}")
            
            # Проверяем кулдаун
            if self.check_cooldown(initiator_id):
                return {
                    'outcome': 'cooldown',
                    'message': f"⏰ {initiator_username}, подожди ещё немного перед следующим броском!",
                    'targets': [(initiator_id, initiator_username)],
                    'initiator_id': initiator_id,
                    'chat_id': chat_id,
                    'error': 'cooldown'
                }
            
            # Проверяем, не является ли цель самим метателем
            if target_id == initiator_id:
                return {
                    'outcome': 'self_target',
                    'message': f"🤡 {initiator_username}, нельзя метать говно в самого себя!",
                    'targets': [(initiator_id, initiator_username)],
                    'initiator_id': initiator_id,
                    'chat_id': chat_id,
                    'error': 'self_target'
                }
            
            # Назначаем роль, если её нет
            if not self.get_user_role(initiator_id):
                role = self.assign_random_role(initiator_id)
                logger.info(f"🎭 Пользователю {initiator_username} назначена роль: {role}")
            
            # Обновляем время последнего броска
            self.record_throw(initiator_id)
            
            # Обновляем фокус на цель
            self.update_focus_stacks(initiator_id, target_id, chat_id)
            
            # Применяем штраф за фокус
            focus_penalty = self.calculate_focus_penalty(initiator_id, target_id, chat_id)
            
            # Для целевого броска используем специальную логику
            # Увеличиваем шанс прямого попадания, но оставляем возможность промаха
            outcomes = ['direct_hit', 'miss', 'splash', 'special']
            weights = [60, 15, 20, 5]  # Базовые веса
            
            # Применяем штраф за фокус
            if focus_penalty > 1.0:
                # Увеличиваем шанс промаха и особых эффектов
                weights[1] = int(weights[1] * focus_penalty)  # miss
                weights[3] = int(weights[3] * focus_penalty)  # special
                # Нормализуем
                total = sum(weights)
                weights = [int(w * 100 / total) for w in weights]
                logger.debug(f"🎯 Применён штраф за фокус: {focus_penalty:.2f}x")
            
            outcome = random.choices(outcomes, weights=weights, k=1)[0]
            
            # Обновляем счетчики комбо и серий
            combo_count = self.update_combo_counter(initiator_id, outcome)
            streak_count = self.update_streak_counter(initiator_id, outcome)
            
            # Обновляем heat и счёт
            self.update_user_heat(initiator_id, 3)  # +3 heat за целевой бросок
            score_delta = 0
            if outcome == 'direct_hit':
                score_delta = 15
            elif outcome == 'miss':
                score_delta = -10
            self.update_user_score(initiator_id, score_delta)
            
            # Получаем текущую роль для публичных сигналов
            current_role = self.get_user_role(initiator_id)
            
            # Формируем сообщение в зависимости от исхода
            if outcome == 'direct_hit':
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               target=target_username)
                targets = [(target_id, target_username)]
            
            elif outcome == 'miss':
                message = self.get_random_message(outcome, initiator=initiator_username)
                targets = [(initiator_id, initiator_username)]
            
            elif outcome == 'splash':
                # Разлетелось - цель + случайные дополнительные
                targets = [(target_id, target_username)]
                # Здесь можно добавить логику для дополнительных целей
                message = self.get_random_message(outcome, 
                                               initiator=initiator_username,
                                               targets=f"{target_username} и других")
            
            elif outcome == 'special':
                # Особые эффекты для целевого броска
                effect_type = random.choice(['boomerang', 'avalanche', 'brick', 'bomb'])
                logger.debug(f"⚡ Особый эффект для целевого броска: {effect_type}")
                
                if effect_type == 'boomerang':
                    message = f"{initiator_username} метнул говно в @{target_username}, но оно вернулось бумерангом! 🤡💩"
                    targets = [(initiator_id, initiator_username)]
                elif effect_type == 'avalanche':
                    message = f"{initiator_username} метнул говно в @{target_username}, но устроил говнолавину! 🌨️💩"
                    targets = [(target_id, target_username)]
                elif effect_type == 'brick':
                    message = f"{initiator_username} метнул говно в @{target_username}, но попал кирпичом! 🧱💩"
                    targets = [(target_id, target_username)]
                elif effect_type == 'bomb':
                    message = f"{initiator_username} метнул говно в @{target_username}, но оно взорвалось! 💣💩"
                    targets = [(target_id, target_username)]
            
            result = {
                'outcome': outcome,
                'message': message,
                'targets': targets,
                'initiator_id': initiator_id,
                'chat_id': chat_id,
                'combo_count': combo_count,
                'streak_count': streak_count,
                'combo_bonus': self.get_combo_bonus(combo_count),
                'streak_bonus': self.get_streak_bonus(streak_count),
                # Новые поля для расширенной механики
                'role_used': current_role,
                'heat_at_throw': self.user_heat.get(initiator_id, 0),
                'focus_stacks': self.focus_stacks.get((initiator_id, target_id, chat_id), 0),
                'score_delta': score_delta,
                'public_signals': self.generate_public_signals(initiator_id, targets, chat_id, current_role)
            }
            
            logger.info(f"✅ Целевой бросок обработан: {outcome} -> {target_username}")
            logger.debug(f"📊 Результат: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки целевого броска: {e}")
            return {
                'outcome': 'miss',
                'message': f"{initiator_username} что-то пошло не так и он обосрался сам 💩",
                'targets': [(initiator_id, initiator_username)],
                'initiator_id': initiator_id,
                'chat_id': chat_id
            }
    
    # ---------------------- Публичные сигналы ----------------------
    def generate_public_signals(self, initiator_id: int, targets: List[Tuple[int, str]], 
                               chat_id: int, role: Optional[str]) -> Dict[str, Any]:
        """Генерирует публичные сигналы после броска"""
        signals = {
            'initiator_role': role,
            'heat_status': self.user_heat.get(initiator_id, 0),
            'under_fire_candidates': [],
            'call_to_action': '',
            'focus_warning': False
        }
        
        # Определяем кандидатов "под прицелом"
        if targets and len(targets) == 1:
            target_id = targets[0][0]
            if target_id != initiator_id:
                # Цель может ответить
                signals['under_fire_candidates'].append({
                    'user_id': target_id,
                    'username': targets[0][1],
                    'can_retaliate': True,
                    'focus_stacks': self.focus_stacks.get((initiator_id, target_id, chat_id), 0)
                })
                
                # Предупреждение о фокусе
                if signals['under_fire_candidates'][0]['focus_stacks'] > 2:
                    signals['focus_warning'] = True
        
        # Формируем призыв к действию
        if signals['under_fire_candidates']:
            target = signals['under_fire_candidates'][0]
            if target['can_retaliate']:
                if target['focus_stacks'] > 2:
                    signals['call_to_action'] = f"🎯 @{target['username']} под прицелом! Фокус: {target['focus_stacks']} ударов"
                else:
                    signals['call_to_action'] = f"🎯 @{target['username']} может ответить! /go @{target['username']}"
        
        return signals
    
    def get_emoji_for_outcome(self, outcome: str) -> str:
        """Получение эмодзи для исхода"""
        emojis = {
            'direct_hit': '🎯💩',
            'miss': '🤡💩',
            'splash': '🤮💩',
            'special': '⚡💩',
            'critical': '💥💩',
            'combo': '🔄💩',
            'legendary': '👑💩',
            'cooldown': '⏰',
            'self_target': '🤡'
        }
        emoji = emojis.get(outcome, '💩')
        logger.debug(f"😀 Эмодзи для исхода {outcome}: {emoji}")
        return emoji
    
    def update_combo_counter(self, user_id: int, outcome: str) -> int:
        """Обновление счетчика комбо для пользователя"""
        if user_id not in self.combo_counters:
            self.combo_counters[user_id] = 0
        
        if outcome in ['direct_hit', 'critical', 'combo']:
            self.combo_counters[user_id] += 1
            logger.debug(f"🔄 Комбо для пользователя {user_id}: {self.combo_counters[user_id]}")
        else:
            self.combo_counters[user_id] = 0
            logger.debug(f"🔄 Сброс комбо для пользователя {user_id}")
        
        return self.combo_counters[user_id]
    
    def update_streak_counter(self, user_id: int, outcome: str) -> int:
        """Обновление счетчика серий для пользователя"""
        if user_id not in self.streak_counters:
            self.streak_counters[user_id] = 0
        
        if outcome in ['direct_hit', 'critical', 'combo', 'legendary']:
            self.streak_counters[user_id] += 1
            logger.debug(f"🔥 Серия для пользователя {user_id}: {self.streak_counters[user_id]}")
        else:
            self.streak_counters[user_id] = 0
            logger.debug(f"🔥 Сброс серии для пользователя {user_id}")
        
        return self.streak_counters[user_id]
    
    def get_combo_bonus(self, combo_count: int) -> float:
        """Получение бонуса за комбо"""
        if combo_count >= 10:
            return 3.0  # Тройной урон
        elif combo_count >= 5:
            return 2.0  # Двойной урон
        elif combo_count >= 3:
            return 1.5  # Полуторный урон
        else:
            return 1.0  # Обычный урон
    
    def get_streak_bonus(self, streak_count: int) -> float:
        """Получение бонуса за серию"""
        if streak_count >= 20:
            return 4.0  # Четверной урон
        elif streak_count >= 15:
            return 3.0  # Тройной урон
        elif streak_count >= 10:
            return 2.5  # Двойной с половиной урон
        elif streak_count >= 5:
            return 2.0  # Двойной урон
        else:
            return 1.0  # Обычный урон
