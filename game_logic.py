import random
import asyncio
from typing import List, Tuple, Dict, Optional
from config import OUTCOME_PROBABILITIES, GAME_MESSAGES
from logger_config import get_logger

logger = get_logger('game')

class GameLogic:
    def __init__(self):
        self.outcomes = list(OUTCOME_PROBABILITIES.keys())
        self.weights = list(OUTCOME_PROBABILITIES.values())
        self.combo_counters = {}  # Счетчики комбо для каждого пользователя
        self.streak_counters = {}  # Счетчики серий для каждого пользователя
        logger.info("🎮 Игровая логика ГовноМёт инициализирована")
    
    def determine_outcome(self, user_id: int = None) -> str:
        """Определение исхода броска на основе вероятностей и комбо"""
        # Базовые вероятности
        base_weights = self.weights.copy()
        
        # Если есть пользователь, применяем бонусы за комбо и серии
        if user_id is not None:
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
            
            # Определяем исход
            outcome = self.determine_outcome(initiator_id)
            
            # Выбираем цели
            targets = self.select_targets(participants, initiator_id, outcome)
            
            # Обновляем счетчики комбо и серий
            combo_count = self.update_combo_counter(initiator_id, outcome)
            streak_count = self.update_streak_counter(initiator_id, outcome)
            
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
                'streak_bonus': self.get_streak_bonus(streak_count)
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
            
            # Для целевого броска используем специальную логику
            # Увеличиваем шанс прямого попадания, но оставляем возможность промаха
            outcomes = ['direct_hit', 'miss', 'splash', 'special']
            weights = [60, 15, 20, 5]  # 60% попадание, 15% промах, 20% разлет, 5% особый эффект
            
            outcome = random.choices(outcomes, weights=weights, k=1)[0]
            
            # Обновляем счетчики комбо и серий
            combo_count = self.update_combo_counter(initiator_id, outcome)
            streak_count = self.update_streak_counter(initiator_id, outcome)
            
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
                    message = f"@{initiator_username} метнул говно в @{target_username}, но оно вернулось бумерангом! 🤡💩"
                    targets = [(initiator_id, initiator_username)]
                elif effect_type == 'avalanche':
                    message = f"@{initiator_username} метнул говно в @{target_username}, но устроил говнолавину! 🌨️💩"
                    targets = [(target_id, target_username)]
                elif effect_type == 'brick':
                    message = f"@{initiator_username} метнул говно в @{target_username}, но попал кирпичом! 🧱💩"
                    targets = [(target_id, target_username)]
                elif effect_type == 'bomb':
                    message = f"@{initiator_username} метнул говно в @{target_username}, но оно взорвалось! 💣💩"
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
                'streak_bonus': self.get_streak_bonus(streak_count)
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
    
    def get_emoji_for_outcome(self, outcome: str) -> str:
        """Получение эмодзи для исхода"""
        emojis = {
            'direct_hit': '🎯💩',
            'miss': '🤡💩',
            'splash': '🤮💩',
            'special': '⚡💩',
            'critical': '💥💩',
            'combo': '🔄💩',
            'legendary': '👑💩'
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
