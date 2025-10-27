"""
Модели данных для Telegram-бота изучения словарных слов
Используют Pydantic для валидации данных
"""

from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


# ============================================================================
# МОДЕЛИ ДЛЯ СЛОВ И СЛОВАРЕЙ
# ============================================================================

class Word(BaseModel):
    """
    Модель одного словарного слова с отслеживанием прогресса
    """
    text: str = Field(..., min_length=1, description="Текст слова")
    consecutive_correct: int = Field(default=0, ge=0, description="Правильные ответы подряд")
    total_attempts: int = Field(default=0, ge=0, description="Всего попыток в сессии")
    correct_count: int = Field(default=0, ge=0, description="Количество правильных ответов")
    incorrect_count: int = Field(default=0, ge=0, description="Количество неправильных ответов")
    is_mastered: bool = Field(default=False, description="Выучено ли на оценку 5")
    priority_score: int = Field(default=100, ge=1, le=100, description="Приоритет для показа")


class Dictionary(BaseModel):
    """
    Модель словаря (коллекции слов)
    """
    id: str = Field(..., description="Уникальный ID словаря")
    name: str = Field(default="Словарь", description="Название словаря")
    words: List[str] = Field(default_factory=list, description="Список слов")
    created_at: datetime = Field(default_factory=datetime.now, description="Дата создания")
    updated_at: Optional[datetime] = Field(default=None, description="Дата последнего обновления")
    is_fully_learned: bool = Field(default=False, description="Все ли слова выучены")
    total_sessions: int = Field(default=0, ge=0, description="Количество сессий обучения")
    last_session_date: Optional[datetime] = Field(default=None, description="Дата последней сессии")


class WordProgress(BaseModel):
    """
    Модель прогресса одного слова в словаре (долгосрочное отслеживание)
    """
    word: str = Field(..., description="Текст слова")
    total_correct: int = Field(default=0, ge=0, description="Всего правильных ответов за все сессии")
    total_incorrect: int = Field(default=0, ge=0, description="Всего неправильных ответов за все сессии")
    times_mastered: int = Field(default=0, ge=0, description="Сколько раз было выучено на 5")
    last_attempted: Optional[datetime] = Field(default=None, description="Последняя попытка")


class UserProgress(BaseModel):
    """
    Модель общего прогресса пользователя
    """
    user_id: int = Field(..., description="ID пользователя в Telegram")
    total_words_learned: int = Field(default=0, ge=0, description="Всего слов выучено на 5")
    total_sessions: int = Field(default=0, ge=0, description="Всего сессий обучения")
    total_attempts: int = Field(default=0, ge=0, description="Всего попыток ответов")
    total_correct: int = Field(default=0, ge=0, description="Всего правильных ответов")
    total_incorrect: int = Field(default=0, ge=0, description="Всего неправильных ответов")
    dictionaries_progress: Dict[str, Dict[str, WordProgress]] = Field(default_factory=dict, description="Прогресс по словарям")
    created_at: datetime = Field(default_factory=datetime.now, description="Дата создания профиля")
    last_activity: Optional[datetime] = Field(default=None, description="Последняя активность")

    @property
    def success_rate(self) -> float:
        """Процент правильных ответов"""
        if self.total_attempts == 0:
            return 0.0
        return (self.total_correct / self.total_attempts) * 100


class SessionStats(BaseModel):
    """
    Модель статистики одной сессии обучения
    """
    session_id: str = Field(..., description="Уникальный ID сессии")
    user_id: int = Field(..., description="ID пользователя")
    dict_id: str = Field(..., description="ID словаря")
    dict_name: str = Field(..., description="Название словаря")
    started_at: datetime = Field(default_factory=datetime.now, description="Время начала")
    ended_at: Optional[datetime] = Field(default=None, description="Время завершения")
    total_words: int = Field(..., ge=1, description="Всего слов в словаре")
    correct_answers: int = Field(default=0, ge=0, description="Правильные ответы")
    incorrect_answers: int = Field(default=0, ge=0, description="Неправильные ответы")
    words_mastered: int = Field(default=0, ge=0, description="Слов выучено на 5")
    words_mastered_list: List[str] = Field(default_factory=list, description="Список выученных слов")

    @property
    def duration_seconds(self) -> int:
        """Длительность сессии в секундах"""
        if not self.ended_at:
            return 0
        return int((self.ended_at - self.started_at).total_seconds())

    @property
    def success_rate(self) -> float:
        """Процент правильных ответов"""
        total = self.correct_answers + self.incorrect_answers
        if total == 0:
            return 0.0
        return (self.correct_answers / total) * 100

    @property
    def is_complete(self) -> bool:
        """Завершена ли сессия (все слова выучены)"""
        return self.words_mastered >= self.total_words
