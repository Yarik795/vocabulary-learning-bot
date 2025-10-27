"""
Вспомогательные функции для работы со словами: хеширование, перемешивание вариантов
"""

import hashlib
import random
import logging
from typing import List, Tuple


logger = logging.getLogger(__name__)


# ============================================================================
# ХЕШИРОВАНИЕ СЛОВ
# ============================================================================

def get_word_hash(word: str) -> str:
    """
    Генерировать хеш для слова для использования в имени файла кэша
    
    Args:
        word: Исходное слово
        
    Returns:
        Хеш слова (8 символов)
    """
    # Нормализуем слово: в нижний регистр и удаляем пробелы
    normalized = word.lower().strip()
    
    # Создаем MD5 хеш
    hash_obj = hashlib.md5(normalized.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Возвращаем первые 8 символов
    return hash_hex[:8]


def get_words_hashes(words: List[str]) -> dict:
    """
    Получить хеши для списка слов
    
    Args:
        words: Список слов
        
    Returns:
        Словарь {слово: хеш}
    """
    return {word: get_word_hash(word) for word in words}


# ============================================================================
# ПЕРЕМЕШИВАНИЕ ВАРИАНТОВ
# ============================================================================

def shuffle_variants(correct_word: str, wrong_variants: List[str]) -> List[str]:
    """
    Перемешать правильное слово с неправильными вариантами
    
    Args:
        correct_word: Правильное слово
        wrong_variants: Список неправильных вариантов (обычно 3 штуки)
        
    Returns:
        Список из 4 вариантов в случайном порядке с индексом правильного
    """
    # Создаем список всех вариантов
    all_variants = [correct_word] + wrong_variants
    
    # Перемешиваем
    random.shuffle(all_variants)
    
    logger.debug(f"🔀 Перемешаны варианты для слова '{correct_word}'")
    
    return all_variants


def get_correct_variant_index(variants: List[str], correct_word: str) -> int:
    """
    Получить индекс правильного варианта в перемешанном списке
    
    Args:
        variants: Список всех вариантов
        correct_word: Правильное слово
        
    Returns:
        Индекс правильного варианта (0-3)
    """
    try:
        return variants.index(correct_word)
    except ValueError:
        logger.error(f"❌ Правильное слово '{correct_word}' не найдено в вариантах: {variants}")
        return -1


# ============================================================================
# ФОРМАТИРОВАНИЕ И ВАЛИДАЦИЯ
# ============================================================================

def is_russian_word(word: str) -> bool:
    """
    Проверить, содержит ли слово только русские буквы и дефис
    
    Args:
        word: Слово для проверки
        
    Returns:
        True если это русское слово, False иначе
    """
    if not word:
        return False
    
    # Русские буквы: А-Я, а-я, ё, Ё
    valid_chars = set('АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя-')
    
    return all(c in valid_chars for c in word)


def validate_variants_uniqueness(variants: List[str], original_word: str) -> Tuple[bool, str]:
    """
    Валидировать, что все варианты уникальны и отличаются от оригинала
    
    Args:
        variants: Список вариантов (easy + medium + hard = 12 штук)
        original_word: Оригинальное слово
        
    Returns:
        (True, "") если валидно, (False, причина) если нет
    """
    if not variants:
        return False, "Пустой список вариантов"
    
    if len(variants) != 12:
        return False, f"Неверное количество вариантов: {len(variants)}, ожидается 12"
    
    # Проверяем уникальность
    unique_variants = set(variants)
    if len(unique_variants) != len(variants):
        duplicates = [v for v in variants if variants.count(v) > 1]
        return False, f"Найдены дубликаты: {set(duplicates)}"
    
    # Проверяем что все отличаются от оригинала
    if original_word.lower() in [v.lower() for v in variants]:
        return False, f"Оригинальное слово присутствует в вариантах"
    
    # Проверяем что все русские
    invalid_variants = [v for v in variants if not is_russian_word(v)]
    if invalid_variants:
        return False, f"Не русские варианты: {invalid_variants}"
    
    return True, ""


def validate_variant_structure(variants_list: list, original_word: str) -> Tuple[bool, str]:
    """
    Валидировать структуру списка вариантов
    
    Args:
        variants_list: Список неправильных вариантов (должно быть 3 штуки)
        original_word: Оригинальное слово (для проверки)
        
    Returns:
        (True, "") если структура корректна, (False, причина) иначе
    """
    # Проверяем что это список
    if not isinstance(variants_list, list):
        return False, f"Варианты должны быть списком, получено: {type(variants_list)}"
    
    # Проверяем количество вариантов
    if len(variants_list) != 3:
        return False, f"Неверное количество вариантов: {len(variants_list)}, ожидается 3"
    
    # Проверяем каждый элемент
    for i, variant in enumerate(variants_list):
        # Проверяем что это строка
        if not isinstance(variant, str):
            return False, f"Вариант {i+1} должен быть строкой, получено: {type(variant)}"
        
        # Проверяем что вариант не пустой
        if not variant.strip():
            return False, f"Вариант {i+1} пустой"
        
        # Проверяем что вариант отличается от оригинала
        if variant.lower() == original_word.lower():
            return False, f"Вариант {i+1} совпадает с оригиналом"
        
        # Проверяем что варианты только русские
        if not is_russian_word(variant):
            return False, f"Вариант {i+1} содержит не-русские буквы: '{variant}'"
    
    return True, ""
