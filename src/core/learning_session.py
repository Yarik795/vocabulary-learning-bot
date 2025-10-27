"""
Менеджер для адаптивной обучающей сессии (Этап 6)
Сессия работает до тех пор пока все слова не выучены на оценку "5"
Слова повторяются с учётом приоритета и сложности вариантов
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path

from config.settings import DATA_DIR, PROGRESS_UPDATE_INTERVAL
from src.core.models import Word, SessionStats
from src.core.adaptive_learning import AdaptiveLearning
from src.utils.file_helpers import save_json, load_json

logger = logging.getLogger(__name__)


class LearningSession:
    """
    Менеджер для адаптивной обучающей сессии (Этап 6)
    
    Особенности:
    - Слова повторяются до полного усвоения (все выучены на 5)
    - Адаптивный выбор: слова с ошибками показываются чаще
    - Адаптивная сложность: варианты подбираются по количеству ошибок
    - Критерий выученности: 3 подряд + 75% успешности + мин 3 попытки
    """
    
    def __init__(self, user_id: int, dict_id: str, dict_name: str, words_list: List[str]):
        """
        Инициализация адаптивной сессии обучения
        
        Args:
            user_id: ID пользователя в Telegram
            dict_id: ID словаря
            dict_name: Название словаря
            words_list: Список слов для обучения
        """
        self.user_id = user_id
        self.dict_id = dict_id
        self.dict_name = dict_name
        
        # Генерируем уникальный ID для сессии
        self.session_id = str(uuid.uuid4())[:8]
        
        # Инициализируем слова как объекты Word с адаптивными параметрами
        self.words: Dict[str, Word] = {
            word: Word(text=word) for word in words_list
        }
        
        # Текущее слово (для показа в интерфейсе)
        self.current_word: Optional[str] = None
        self.total_words_shown = 0  # Сколько раз показали любое слово (для промежуточного прогресса)
        
        # Статистика сессии
        self.stats = SessionStats(
            session_id=self.session_id,
            user_id=user_id,
            dict_id=dict_id,
            dict_name=dict_name,
            started_at=datetime.now(),
            total_words=len(words_list)
        )
        
        logger.info(f"✅ AdaptiveLearningSession создана: сессия={self.session_id}, слов={len(words_list)}")
    
    
    def get_next_word(self) -> Optional[str]:
        """
        Получить следующее слово для показа на основе приоритета адаптивного алгоритма
        
        Логика:
        1. Если все слова выучены - возвращаем None (сессия завершена)
        2. Иначе - выбираем невыученное слово с наивысшим приоритетом
           - Слова с ошибками показываются в первую очередь
           - Слова с высоким priority_score показываются раньше
        
        Returns:
            Текст слова или None если все выучены
        """
        try:
            # Проверяем завершена ли сессия
            if AdaptiveLearning.is_session_complete(self.words):
                logger.info("🎉 СЕССИЯ ЗАВЕРШЕНА! ВСЕ СЛОВА ВЫУЧЕНЫ НА 5!")
                return None
            
            # Выбираем следующее слово по приоритету
            next_word = AdaptiveLearning.get_next_word_by_priority(self.words)
            
            if next_word is None:
                logger.info("🎉 ВСЕ СЛОВА ВЫУЧЕНЫ НА ОЦЕНКУ 5!")
                return None
            
            self.current_word = next_word
            self.total_words_shown += 1
            
            return next_word
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении следующего слова: {e}")
            return None
    
    
    def get_current_word(self) -> Optional[str]:
        """Получить текущее слово (которое показано)"""
        return self.current_word
    
    
    def get_word_data(self, word: str) -> Optional[Word]:
        """
        Получить объект Word по тексту
        
        Args:
            word: Текст слова
            
        Returns:
            Объект Word или None
        """
        return self.words.get(word)
    
    
    def get_difficulty_for_word(self, word: str) -> Dict[str, int]:
        """
        Получить уровень сложности вариантов для слова
        
        Сложность выбирается на основе количества ошибок:
        - 0 ошибок: только сложные варианты (hard x3)
        - 1-2 ошибки: средние и сложные (medium x1 + hard x2)
        - 3+ ошибок: лёгкие и средние (easy x1 + medium x2) - помощь ученику
        
        Args:
            word: Текст слова
            
        Returns:
            Dict: {'easy': N, 'medium': N, 'hard': N}
        """
        try:
            word_obj = self.words.get(word)
            if not word_obj:
                return {"easy": 0, "medium": 0, "hard": 3}
            
            difficulty = AdaptiveLearning.get_difficulty_level(word_obj.incorrect_count)
            logger.debug(f"🎯 Уровень сложности для '{word}' (ошибок: {word_obj.incorrect_count}): {difficulty}")
            
            return difficulty
        
        except Exception as e:
            logger.error(f"❌ Ошибка при определении сложности: {e}")
            return {"easy": 0, "medium": 0, "hard": 3}
    
    
    def record_answer(self, word: str, is_correct: bool) -> bool:
        """
        Записать результат ответа и обновить статус слова через адаптивный алгоритм
        
        Args:
            word: Текст слова
            is_correct: True если ответ правильный
            
        Returns:
            True если успешно
        """
        try:
            word_obj = self.words.get(word)
            if not word_obj:
                logger.error(f"❌ Слово '{word}' не найдено в сессии")
                return False
            
            # Обновляем статус слова через адаптивный алгоритм
            AdaptiveLearning.update_word_status(word_obj, is_correct)
            
            # Обновляем статистику сессии
            if is_correct:
                self.stats.correct_answers += 1
                logger.debug(f"✅ Ответ правильный для слова '{word}'")
            else:
                self.stats.incorrect_answers += 1
                logger.debug(f"❌ Ответ неправильный для слова '{word}'")
            
            # Проверяем выучено ли слово на 5
            if word_obj.is_mastered:
                if word not in self.stats.words_mastered_list:
                    self.stats.words_mastered_list.append(word)
                    self.stats.words_mastered += 1
                    logger.info(f"✨ Слово '{word}' ВЫУЧЕНО НА 5! Осталось: {len(self.words) - self.stats.words_mastered}")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка при записи ответа: {e}")
            return False
    
    
    def is_complete(self) -> bool:
        """
        Проверить завершена ли сессия (все слова выучены на 5)
        
        Returns:
            True если все слова выучены
        """
        return AdaptiveLearning.is_session_complete(self.words)
    
    
    def get_mastered_count(self) -> int:
        """
        Получить количество выученных слов на оценку 5
        
        Returns:
            Количество выученных слов
        """
        return len([w for w in self.words.values() if w.is_mastered])
    
    
    def get_current_position(self) -> int:
        """
        Получить номер текущего вопроса (количество показанных слов)
        
        Returns:
            Номер вопроса (начиная с 1)
        """
        return self.total_words_shown
    
    
    def get_progress_percentage(self) -> int:
        """
        Получить процент выученных слов
        
        Returns:
            Процент от 0 до 100
        """
        if not self.words:
            return 0
        mastered = self.get_mastered_count()
        return int((mastered / len(self.words)) * 100)
    
    
    def should_show_progress_update(self) -> bool:
        """
        Проверить нужно ли показать промежуточный прогресс
        Показываем каждые PROGRESS_UPDATE_INTERVAL ответов
        
        Returns:
            True если нужно показать прогресс
        """
        total_answers = self.stats.correct_answers + self.stats.incorrect_answers
        return total_answers > 0 and total_answers % PROGRESS_UPDATE_INTERVAL == 0
    
    
    def get_progress_update(self) -> str:
        """
        Получить текст промежуточного обновления прогресса
        
        Returns:
            Форматированная строка с прогрессом
        """
        try:
            progress = AdaptiveLearning.get_session_progress(self.words)
            
            emoji_completion = "█" * progress["mastered"] + "░" * progress["remaining"]
            
            total_answers = self.stats.correct_answers + self.stats.incorrect_answers
            success_rate = (self.stats.correct_answers / total_answers * 100) if total_answers > 0 else 0
            
            progress_text = f"""📊 **ПРОМЕЖУТОЧНЫЙ ПРОГРЕСС** 📊

📚 Прогресс: [{emoji_completion}]
• Выучено: {progress['mastered']}/{progress['total']} слов
• Слов с ошибками: {progress['with_errors']}
• Слов без ошибок: {progress['without_errors']}

📈 Статистика:
• Всего ответов: {total_answers}
• Правильно: {self.stats.correct_answers}
• Неправильно: {self.stats.incorrect_answers}
• Процент успеха: {success_rate:.1f}%

💪 Продолжай! Ты на правильном пути!"""
            
            return progress_text
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении прогресса: {e}")
            return "❌ Ошибка при загрузке прогресса"
    
    
    def finish_session(self) -> SessionStats:
        """
        Завершить сессию и вернуть финальную статистику
        
        Returns:
            Объект SessionStats с полной информацией
        """
        self.stats.ended_at = datetime.now()
        
        total_answers = self.stats.correct_answers + self.stats.incorrect_answers
        success_rate = (self.stats.correct_answers / total_answers * 100) if total_answers > 0 else 0
        
        logger.info(f"""
        🎉 СЕССИЯ ЗАВЕРШЕНА:
        • ID сессии: {self.session_id}
        • Всего слов в словаре: {self.stats.total_words}
        • Выучено на 5: {self.stats.words_mastered}
        • Всего ответов: {total_answers}
        • Правильных ответов: {self.stats.correct_answers} ({success_rate:.1f}%)
        • Неправильных ответов: {self.stats.incorrect_answers}
        • Время обучения: {self.stats.duration_seconds} сек
        • Выученные слова: {', '.join(self.stats.words_mastered_list)}
        """)
        
        return self.stats
    
    
    def get_summary(self) -> str:
        """
        Получить итоговую статистику сессии
        
        Returns:
            Форматированная строка с итогами
        """
        minutes, seconds = divmod(self.stats.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        total_answers = self.stats.correct_answers + self.stats.incorrect_answers
        success_rate = (self.stats.correct_answers / total_answers * 100) if total_answers > 0 else 0
        
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"
        
        summary = f"""🎉 **ПОЗДРАВЛЯЮ!** 🎉

ВСЕ СЛОВА ВЫУЧЕНЫ НА ОТЛИЧНО! 🌟

📊 **ИТОГОВАЯ СТАТИСТИКА:**
• Всего слов: {self.stats.total_words}
• Выучено на 5: {self.stats.words_mastered}
• Всего ответов: {total_answers}
• Правильно: {self.stats.correct_answers}
• Неправильно: {self.stats.incorrect_answers}
• Успешность: {success_rate:.1f}%
• Время обучения: {time_str}

📚 **ВЫУЧЕННЫЕ СЛОВА:**
{self._format_mastered_words()}

💪 **ОТЛИЧНАЯ РАБОТА!** 💪
Ты проделал большую работу! Продолжай в том же духе!"""
        
        return summary
    
    
    def _format_mastered_words(self) -> str:
        """Форматировать список выученных слов"""
        try:
            if not self.stats.words_mastered_list:
                return "Нет"
            
            # Группируем по 3 слова в строку
            words = self.stats.words_mastered_list
            lines = []
            for i in range(0, len(words), 3):
                chunk = words[i:i+3]
                lines.append(" • " + ", ".join(chunk))
            
            return "\n".join(lines)
        
        except Exception as e:
            logger.error(f"❌ Ошибка при форматировании слов: {e}")
            return "❌ Ошибка при загрузке списка слов"
