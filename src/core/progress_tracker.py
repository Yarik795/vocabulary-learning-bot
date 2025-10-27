"""
Отслеживание долгосрочного прогресса по словам и словарям
Сохраняет данные между сессиями в progress.json
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from config.settings import DATA_DIR
from src.core.models import WordProgress, UserProgress
from src.utils.file_helpers import save_json, load_json

logger = logging.getLogger(__name__)


class ProgressTracker:
    """
    Менеджер для отслеживания прогресса пользователя по словам и словарям
    Сохраняет данные в data/users/{user_id}/progress.json
    """
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.user_data_dir = DATA_DIR / "users" / str(user_id)
        self.progress_file = self.user_data_dir / "progress.json"
        self.progress = self._load_progress()
    
    
    def _load_progress(self) -> UserProgress:
        """
        Загрузить прогресс пользователя из файла
        
        Returns:
            UserProgress объект
        """
        try:
            if self.progress_file.exists():
                data = load_json(str(self.progress_file))
                if data:
                    # Явная конвертация Dict[str, dict] → Dict[str, WordProgress]
                    if 'dictionaries_progress' in data:
                        for dict_id, dict_words in data['dictionaries_progress'].items():
                            if isinstance(dict_words, dict):
                                for word, word_data in dict_words.items():
                                    if isinstance(word_data, dict):
                                        dict_words[word] = WordProgress(**word_data)
                    
                    return UserProgress(**data)
            
            # Если файла нет - создаём новый прогресс
            logger.info(f"📝 Создан новый прогресс для пользователя {self.user_id}")
            return UserProgress(user_id=self.user_id)
        
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке прогресса: {e}")
            return UserProgress(user_id=self.user_id)
    
    
    def _save_progress(self) -> bool:
        """
        Сохранить прогресс в файл
        
        Returns:
            True если успешно, False иначе
        """
        try:
            # Обновляем время последней активности
            self.progress.last_activity = datetime.now()
            
            # Конвертируем в dict для JSON
            progress_dict = self.progress.model_dump(mode='json')
            
            # Сохраняем файл
            save_json(str(self.progress_file), progress_dict)
            logger.debug(f"✅ Прогресс сохранён для пользователя {self.user_id}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении прогресса: {e}")
            return False
    
    
    def update_word_progress(self, dict_id: str, word: str, is_correct: bool, is_mastered: bool) -> bool:
        """
        Обновить прогресс одного слова
        
        Args:
            dict_id: ID словаря
            word: Текст слова
            is_correct: Правильный ли был ответ
            is_mastered: Выучено ли слово на 5
            
        Returns:
            True если успешно обновлено
        """
        try:
            # Получаем или создаём словарь для этого словаря
            if dict_id not in self.progress.dictionaries_progress:
                self.progress.dictionaries_progress[dict_id] = {}
            
            dict_progress = self.progress.dictionaries_progress[dict_id]
            
            # Получаем или создаём прогресс для слова
            if word not in dict_progress:
                word_progress = WordProgress(word=word)
                dict_progress[word] = word_progress
            else:
                word_progress = dict_progress[word]
            
            # Обновляем статистику
            if is_correct:
                word_progress.total_correct += 1
            else:
                word_progress.total_incorrect += 1
            
            word_progress.last_attempted = datetime.now()
            
            # Если слово только что выучено
            if is_mastered and not word_progress.times_mastered:
                word_progress.times_mastered = 1
            elif is_mastered:
                word_progress.times_mastered += 1
            
            # Обновляем общий прогресс
            self.progress.total_attempts += 1
            if is_correct:
                self.progress.total_correct += 1
            else:
                self.progress.total_incorrect += 1
            
            # Проверяем если слово выучено на 5 в первый раз
            if is_mastered and word_progress.times_mastered == 1:
                self.progress.total_words_learned += 1
            
            # Сохраняем
            return self._save_progress()
        
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении прогресса слова '{word}': {e}")
            return False
    
    
    def update_session_stats(self, dict_id: str, correct_count: int, incorrect_count: int, words_mastered: List[str]) -> bool:
        """
        Обновить статистику по завершённой сессии
        
        Args:
            dict_id: ID словаря
            correct_count: Количество правильных ответов
            incorrect_count: Количество неправильных ответов
            words_mastered: Список слов которые были выучены на 5 в этой сессии
            
        Returns:
            True если успешно
        """
        try:
            # Обновляем общий прогресс
            self.progress.total_sessions += 1
            self.progress.total_correct += correct_count
            self.progress.total_incorrect += incorrect_count
            
            # Добавляем новые выученные слова (только если слово выучено в первый раз)
            dict_progress = self.progress.dictionaries_progress.get(dict_id, {})
            for word in words_mastered:
                word_progress = dict_progress.get(word)
                # Увеличиваем счётчик только если это новое выученное слово
                if word_progress and word_progress.times_mastered == 1:
                    self.progress.total_words_learned += 1
            
            return self._save_progress()
        
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении статистики сессии: {e}")
            return False
    
    
    def get_word_progress(self, dict_id: str, word: str) -> Optional[WordProgress]:
        """
        Получить прогресс одного слова
        
        Args:
            dict_id: ID словаря
            word: Текст слова
            
        Returns:
            WordProgress объект или None
        """
        try:
            dict_progress = self.progress.dictionaries_progress.get(dict_id, {})
            return dict_progress.get(word)
        except Exception as e:
            logger.error(f"❌ Ошибка при получении прогресса слова: {e}")
            return None
    
    
    def get_dictionary_progress(self, dict_id: str) -> Dict:
        """
        Получить прогресс по словарю
        
        Args:
            dict_id: ID словаря
            
        Returns:
            Dict с статистикой словаря
        """
        try:
            dict_progress = self.progress.dictionaries_progress.get(dict_id, {})
            
            if not dict_progress:
                return {
                    "total_words": 0,
                    "words_mastered": 0,
                    "success_rate": 0.0,
                    "total_attempts": 0,
                    "total_correct": 0,
                    "total_incorrect": 0,
                    "last_activity": None
                }
            
            total_words = len(dict_progress)
            words_mastered = sum(1 for wp in dict_progress.values() if wp.times_mastered > 0)
            total_attempts = sum(wp.total_correct + wp.total_incorrect for wp in dict_progress.values())
            total_correct = sum(wp.total_correct for wp in dict_progress.values())
            total_incorrect = sum(wp.total_incorrect for wp in dict_progress.values())
            
            success_rate = (total_correct / total_attempts * 100) if total_attempts > 0 else 0
            
            return {
                "total_words": total_words,
                "words_mastered": words_mastered,
                "success_rate": success_rate,
                "total_attempts": total_attempts,
                "total_correct": total_correct,
                "total_incorrect": total_incorrect,
                "last_activity": max([wp.last_attempted for wp in dict_progress.values() if wp.last_attempted], default=None)
            }
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении прогресса словаря: {e}")
            return {}
    
    
    def get_total_progress(self) -> Dict:
        """
        Получить общий прогресс пользователя
        
        Returns:
            Dict с общей статистикой
        """
        try:
            total_attempts = self.progress.total_attempts
            total_correct = self.progress.total_correct
            
            success_rate = (total_correct / total_attempts * 100) if total_attempts > 0 else 0
            
            return {
                "total_sessions": self.progress.total_sessions,
                "total_words_learned": self.progress.total_words_learned,
                "total_attempts": total_attempts,
                "total_correct": total_correct,
                "total_incorrect": self.progress.total_incorrect,
                "success_rate": success_rate,
                "last_activity": self.progress.last_activity.isoformat() if self.progress.last_activity else None
            }
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении общего прогресса: {e}")
            return {}
    
    
    def get_summary_text(self) -> str:
        """
        Получить текст сводки по прогрессу
        
        Returns:
            Форматированная строка с информацией о прогрессе
        """
        try:
            total = self.get_total_progress()
            
            summary = f"""📊 **ВАШ ПРОГРЕСС** 📊

📚 **Всего статистики:**
• Пройдено сессий: {total['total_sessions']}
• Слов выучено на 5: {total['total_words_learned']}
• Всего попыток: {total['total_attempts']}
• Успешных ответов: {total['total_correct']}
• Процент успехов: {total['success_rate']:.1f}%"""
            
            return summary
        
        except Exception as e:
            logger.error(f"❌ Ошибка при формировании сводки: {e}")
            return "❌ Ошибка при загрузке прогресса"
