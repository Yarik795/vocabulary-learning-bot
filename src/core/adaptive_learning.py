"""
Алгоритм адаптивного повторения в рамках одной сессии обучения
Слова повторяются до полного усвоения (оценка 5) на основе приоритета
"""

import logging
from typing import List, Optional, Dict
from config.settings import (
    MASTERY_CONSECUTIVE_CORRECT,
    MASTERY_MIN_ATTEMPTS,
    MASTERY_SUCCESS_RATE
)
from src.core.models import Word

logger = logging.getLogger(__name__)


class AdaptiveLearning:
    """
    Алгоритм адаптивного обучения в рамках одной сессии
    
    Критерий выученности слова на оценку "5":
    1. consecutive_correct >= 3 (3 правильных ответа подряд без ошибок)
    2. total_attempts >= 3 (минимум 3 попытки)
    3. correct_count >= 3 (минимум 3 правильных ответа)
    4. correct_count / total_attempts >= 0.75 (75% успешности)
    """
    
    @staticmethod
    def update_word_status(word: Word, is_correct: bool) -> bool:
        """
        Обновить статус слова после ответа
        
        Args:
            word: Объект Word для обновления
            is_correct: Правильный ли был ответ
            
        Returns:
            True если статус был обновлён успешно
        """
        try:
            if is_correct:
                # При правильном ответе
                word.consecutive_correct += 1
                word.correct_count += 1
                word.total_attempts += 1
                
                # Проверяем критерии выученности
                if AdaptiveLearning.is_word_mastered(word):
                    word.is_mastered = True
                    logger.info(f"✨ Слово '{word.text}' ВЫУЧЕНО на оценку 5!")
                
                # Снижаем приоритет (показывать реже)
                word.priority_score = max(1, word.priority_score - 20)
                logger.debug(f"✅ Правильный ответ: '{word.text}' (подряд: {word.consecutive_correct}, попыток: {word.total_attempts})")
            
            else:
                # При неправильном ответе
                word.consecutive_correct = 0  # СБРОС серии!
                word.incorrect_count += 1
                word.total_attempts += 1
                word.is_mastered = False  # Отменяем выученность если была
                
                # Повышаем приоритет (показывать чаще)
                word.priority_score = min(100, word.priority_score + 30)
                logger.debug(f"❌ Неправильный ответ: '{word.text}' (ошибок: {word.incorrect_count}, попыток: {word.total_attempts})")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении статуса слова '{word.text}': {e}")
            return False
    
    
    @staticmethod
    def is_word_mastered(word: Word) -> bool:
        """
        Проверить выучено ли слово на оценку "5"
        
        Критерии (ВСЕ должны быть выполнены):
        1. consecutive_correct >= MASTERY_CONSECUTIVE_CORRECT (3 подряд)
        2. total_attempts >= MASTERY_MIN_ATTEMPTS (минимум 3)
        3. correct_count >= MASTERY_MIN_ATTEMPTS (минимум 3)
        4. correct_count / total_attempts >= MASTERY_SUCCESS_RATE (75%)
        
        Args:
            word: Объект Word для проверки
            
        Returns:
            True если слово выучено на 5
        """
        # Критерий 1: 3 подряд правильных
        if word.consecutive_correct < MASTERY_CONSECUTIVE_CORRECT:
            return False
        
        # Критерий 2: минимум 3 попытки
        if word.total_attempts < MASTERY_MIN_ATTEMPTS:
            return False
        
        # Критерий 3: минимум 3 правильных ответа
        if word.correct_count < MASTERY_MIN_ATTEMPTS:
            return False
        
        # Критерий 4: 75% успешности
        success_rate = word.correct_count / word.total_attempts if word.total_attempts > 0 else 0
        if success_rate < MASTERY_SUCCESS_RATE:
            return False
        
        return True
    
    
    @staticmethod
    def get_next_word_by_priority(words: Dict[str, Word]) -> Optional[str]:
        """
        Выбрать следующее слово для показа на основе приоритета
        
        Логика выбора:
        1. Только не выученные слова (is_mastered == False)
        2. Если нет не выученных → None (сессия завершена)
        3. Сортировка по приоритету:
           - Слова с recent errors (incorrect_count > 0 и consecutive_correct == 0)
           - Слова с наибольшим priority_score
           - Слова, которые давно не показывались
        
        Args:
            words: Словарь слов {text: Word}
            
        Returns:
            Текст слова для показа или None если все выучены
        """
        try:
            # Фильтруем невыученные слова
            unmastered_words = [
                (text, word) for text, word in words.items()
                if not word.is_mastered
            ]
            
            # Логируем исключённые слова (уже выученные)
            mastered_words = [text for text, word in words.items() if word.is_mastered]
            if mastered_words:
                logger.debug(f"🏆 Уже выученные слова (исключены): {', '.join(mastered_words)}")
            
            # Если все слова выучены → сессия завершена
            if not unmastered_words:
                logger.info("🎉 ВСЕ СЛОВА ВЫУЧЕНЫ НА ОЦЕНКУ 5!")
                return None
            
            # Сортируем по приоритету
            # 1. Приоритет: слова с недавними ошибками (error_count > 0 и consecutive_correct == 0)
            # 2. Затем: по priority_score (выше = важнее)
            # 3. Затем: по общему количеству попыток (меньше = показывали реже)
            
            def sort_key(item):
                text, word = item
                # Слова с недавними ошибками (не выучены и были ошибки) - наивысший приоритет
                has_recent_error = word.incorrect_count > 0 and word.consecutive_correct == 0
                
                # Возвращаем tuple для сортировки:
                # - Сначала по recent_error (True перед False)
                # - Потом по priority_score (выше перед ниже)
                # - Потом по total_attempts (меньше перед больше)
                return (-int(has_recent_error), -word.priority_score, word.total_attempts)
            
            unmastered_words.sort(key=sort_key)
            
            # Возвращаем слово с наивысшим приоритетом
            selected_word = unmastered_words[0][0]
            selected_obj = unmastered_words[0][1]
            
            # Добавляю дополнительную проверку
            if selected_obj.is_mastered:
                logger.warning(f"⚠️ ВНИМАНИЕ! Слово '{selected_word}' отмечено как выученное, но попало в пул невыученных. Пропускаем.")
                # Рекурсивно попробуем найти следующее слово (исключая текущее)
                words_filtered = {k: v for k, v in words.items() if k != selected_word}
                if words_filtered:
                    return AdaptiveLearning.get_next_word_by_priority(words_filtered)
                else:
                    return None
            
            logger.debug(f"🎯 Выбрано слово: '{selected_word}' (приоритет: {selected_obj.priority_score}, ошибок: {selected_obj.incorrect_count}, попыток: {selected_obj.total_attempts})")
            
            return selected_word
        
        except Exception as e:
            logger.error(f"❌ Ошибка при выборе следующего слова: {e}")
            return None
    
    
    @staticmethod
    def get_difficulty_level(incorrect_count: int) -> Dict[str, int]:
        """
        Определить сложность вариантов на основе количества ошибок
        
        Логика:
        - incorrect_count == 0: только сложные варианты (hard x3)
        - incorrect_count == 1-2: средние и сложные (medium x1 + hard x2)
        - incorrect_count >= 3: лёгкие и средние (easy x1 + medium x2) - помощь
        
        Args:
            incorrect_count: Количество ошибок для слова
            
        Returns:
            Dict с количеством вариантов каждой сложности: {'easy': N, 'medium': N, 'hard': N}
        """
        # План 0009: распределение по сложности больше не используется
        # Возвращаем стандартное распределение для совместимости
        difficulty_map = {
            0: {"hard": 3, "medium": 0, "easy": 0},
            1: {"hard": 2, "medium": 1, "easy": 0},
            2: {"hard": 2, "medium": 1, "easy": 0},
        }
        if incorrect_count >= 3:
            return {"easy": 1, "medium": 2, "hard": 0}
        return difficulty_map.get(incorrect_count, {"hard": 3, "medium": 0, "easy": 0})
    
    
    @staticmethod
    def is_session_complete(words: Dict[str, Word]) -> bool:
        """
        Проверить завершена ли сессия (все слова выучены на 5)
        
        Args:
            words: Словарь слов {text: Word}
            
        Returns:
            True если все слова выучены, False иначе
        """
        if not words:
            return True
        
        all_mastered = all(word.is_mastered for word in words.values())
        
        if all_mastered:
            logger.info("🎉 СЕССИЯ УСПЕШНО ЗАВЕРШЕНА! ВСЕ СЛОВА ВЫУЧЕНЫ НА 5!")
        
        return all_mastered
    
    
    @staticmethod
    def get_session_progress(words: Dict[str, Word]) -> Dict[str, int]:
        """
        Получить прогресс сессии
        
        Returns:
            Dict с статистикой:
            - mastered: количество выученных слов
            - total: всего слов
            - with_errors: слова где были ошибки
            - without_errors: слова где не было ошибок
        """
        try:
            mastered = sum(1 for word in words.values() if word.is_mastered)
            total = len(words)
            with_errors = sum(1 for word in words.values() if word.incorrect_count > 0)
            without_errors = total - with_errors
            
            return {
                "mastered": mastered,
                "total": total,
                "with_errors": with_errors,
                "without_errors": without_errors,
                "remaining": total - mastered
            }
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении прогресса: {e}")
            return {"mastered": 0, "total": 0, "with_errors": 0, "without_errors": 0, "remaining": 0}
