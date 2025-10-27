"""
Генератор клавиатур для Telegram бота
Функции: главное меню, варианты ответа, действия
"""

import logging
from typing import List
from aiogram.utils.keyboard import InlineKeyboardBuilder
from src.utils.word_helpers import shuffle_variants
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


# ============================================================================
# ФУНКЦИИ ФОРМАТИРОВАНИЯ (План 0012)
# ============================================================================

def get_learning_progress_text(mastered: int, total: int, question_number: int) -> str:
    """
    Форматировать текст прогресса обучения
    
    ✅ План 0012: Функция для единообразного показа прогресса
    
    Args:
        mastered: Количество выученных слов
        total: Общее количество слов
        question_number: Номер текущего вопроса
        
    Returns:
        Форматированная строка прогресса
    """
    return f"📊 Выучено: {mastered}/{total} | Вопрос #{question_number}"


def get_main_menu_keyboard():
    """
    Создать главное меню с основными кнопками
    
    Returns:
        InlineKeyboardMarkup с кнопками главного меню
    """
    keyboard = InlineKeyboardBuilder()
    
    keyboard.button(text="📸 Загрузить фото", callback_data="upload_photo")
    keyboard.button(text="📚 Мои словари", callback_data="view_dictionaries")
    keyboard.button(text="📊 Мой прогресс", callback_data="show_progress")
    keyboard.button(text="❓ Помощь", callback_data="show_help")
    
    keyboard.adjust(2)
    
    return keyboard.as_markup()


def get_dictionary_list_keyboard(dictionaries):
    """
    Создать клавиатуру со списком словарей
    
    Args:
        dictionaries: Список объектов Dictionary
        
    Returns:
        InlineKeyboardMarkup с кнопками словарей
    """
    keyboard = InlineKeyboardBuilder()
    
    for dictionary in dictionaries:
        button_text = f"📖 {dictionary.name} ({len(dictionary.words)} слов)"
        button_data = f"dict_select:{dictionary.id}"
        keyboard.button(text=button_text, callback_data=button_data)
    
    keyboard.button(text="➕ Создать новый", callback_data="upload_photo")
    keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
    
    keyboard.adjust(1)
    
    return keyboard.as_markup()


def get_answer_variants_keyboard(correct_word: str, wrong_variants: List[str]) -> dict:
    """
    Создать inline клавиатуру с вариантами ответа
    
    Алгоритм:
    1. Берём правильное слово + 3 неправильных варианта
    2. Перемешиваем их
    3. Создаём кнопки в виде сетки 2x2
    
    Args:
        correct_word: Правильное слово
        wrong_variants: Список из 3 неправильных вариантов
        
    Returns:
        Словарь с:
        - 'keyboard': InlineKeyboardMarkup объект
        - 'variants': Список вариантов в порядке показа [вариант1, вариант2, вариант3, вариант4]
    """
    try:
        # Валидация входных данных
        if not correct_word or not isinstance(wrong_variants, list):
            logger.error(f"❌ Ошибка в get_answer_variants_keyboard: некорректные входные данные")
            return None
        
        if len(wrong_variants) < 3:
            logger.warning(f"⚠️ Недостаточно неправильных вариантов ({len(wrong_variants)}/3)")
            # Используем то что есть
            variants_to_use = wrong_variants
        else:
            variants_to_use = wrong_variants[:3]  # Берём первые 3
        
        # Перемешиваем варианты
        all_variants = shuffle_variants(correct_word, variants_to_use)
        
        # Создаём клавиатуру
        keyboard = InlineKeyboardBuilder()
        
        for variant in all_variants:
            is_correct = (variant == correct_word)
            callback_data = f"answer:{correct_word}:{variant}"
            keyboard.button(text=variant, callback_data=callback_data)
        
        # Располагаем кнопки 2x2
        keyboard.adjust(2, 2)
        
        logger.debug(f"✅ Клавиатура создана: варианты={all_variants}")
        
        return {
            'keyboard': keyboard.as_markup(),
            'variants': all_variants
        }
    
    except Exception as e:
        logger.error(f"❌ Ошибка при создании клавиатуры ответов: {e}")
        return None


def get_answer_variants_keyboard_with_pause(correct_word: str, wrong_variants: List[str], session_id: str) -> dict:
    """
    Создать inline клавиатуру с вариантами ответа И кнопкой паузы (ПРОБЛЕМА #1)
    
    Args:
        correct_word: Правильное слово
        wrong_variants: Список из 3 неправильных вариантов
        session_id: ID сессии для кнопки паузы
        
    Returns:
        Словарь с:
        - 'keyboard': InlineKeyboardMarkup объект с вариантами и кнопкой паузы
        - 'variants': Список вариантов в порядке показа
    """
    try:
        # Валидация входных данных
        if not correct_word or not isinstance(wrong_variants, list):
            logger.error(f"❌ Ошибка в get_answer_variants_keyboard_with_pause: некорректные входные данные")
            return None
        
        if len(wrong_variants) < 3:
            logger.warning(f"⚠️ Недостаточно неправильных вариантов ({len(wrong_variants)}/3)")
            variants_to_use = wrong_variants
        else:
            variants_to_use = wrong_variants[:3]
        
        # Перемешиваем варианты
        all_variants = shuffle_variants(correct_word, variants_to_use)
        
        # Создаём клавиатуру
        keyboard = InlineKeyboardBuilder()
        
        # Добавляем варианты ответов в сетке 2x2
        for variant in all_variants:
            callback_data = f"answer:{correct_word}:{variant}"
            keyboard.button(text=variant, callback_data=callback_data)
        
        keyboard.adjust(2, 2)
        
        # Добавляем кнопку паузы отдельной строкой
        from aiogram.types import InlineKeyboardButton
        pause_button = InlineKeyboardButton(
            text="⏸️ Пауза",
            callback_data=f"pause_session:{session_id}"
        )
        keyboard.row(pause_button)
        
        logger.debug(f"✅ Клавиатура с паузой создана: варианты={all_variants}, session={session_id}")
        
        return {
            'keyboard': keyboard.as_markup(),
            'variants': all_variants
        }
    
    except Exception as e:
        logger.error(f"❌ Ошибка при создании клавиатуры с паузой: {e}")
        return None


def get_end_session_keyboard() -> dict:
    """
    Создать клавиатуру для конца сессии
    
    Returns:
        InlineKeyboardMarkup с вариантами действий после сессии
    """
    keyboard = InlineKeyboardBuilder()
    
    keyboard.button(text="📚 Мои словари", callback_data=f"view_dictionaries")
    keyboard.button(text="🎓 Начать заново", callback_data=f"repeat_learning")
    keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
    
    keyboard.adjust(2, 1)
    
    return keyboard.as_markup()


def get_learning_session_keyboard(user_id: int, session_id: str) -> dict:
    """
    Создать клавиатуру для сессии обучения с кнопкой пауза
    
    Args:
        user_id: ID пользователя
        session_id: ID сессии
        
    Returns:
        InlineKeyboardMarkup с кнопкой паузы
    """
    keyboard = InlineKeyboardBuilder()
    
    keyboard.button(text="⏸️ Пауза", callback_data=f"pause_session:{session_id}")
    
    keyboard.adjust(1)
    
    return keyboard.as_markup()


def get_session_paused_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру для паузы сессии
    
    Args:
        session_id: ID сессии
        
    Returns:
        InlineKeyboardMarkup с вариантами продолжить или завершить
    """
    keyboard = InlineKeyboardBuilder()
    
    keyboard.button(text="▶️ Продолжить обучение", callback_data=f"resume_session:{session_id}")
    keyboard.button(text="⏹️ Завершить сессию", callback_data=f"end_paused_session:{session_id}")
    keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
    
    keyboard.adjust(1)
    
    return keyboard.as_markup()


def get_edit_keyboard():
    """
    Создать клавиатуру для редактирования словаря
    
    Returns:
        InlineKeyboardMarkup с кнопками редактирования
    """
    keyboard = InlineKeyboardBuilder()
    
    keyboard.button(text="✅ Готово", callback_data="confirm_edit")
    keyboard.button(text="❌ Отмена", callback_data="cancel_edit")
    
    keyboard.adjust(2)
    
    return keyboard.as_markup()
