"""Состояния Telegram бота"""

from aiogram.fsm.state import State, StatesGroup


class DictionaryStates(StatesGroup):
    """Состояния для работы со словарями"""
    waiting_for_words = State()  # Ожидание отредактированного списка слов


class LearningSessionStates(StatesGroup):
    """Состояния для сессии обучения"""
    in_session = State()  # В процессе сессии обучения
    waiting_for_answer = State()  # Ожидание ответа пользователя
    session_paused = State()  # Сессия на паузе (ИСПРАВЛЕНИЕ ПРОБЛЕМА #4)
