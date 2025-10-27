"""
Валидация и очистка слов после распознавания
"""

import logging
import re
from typing import List, Set

from config.settings import MAX_WORDS_IN_DICTIONARY


logger = logging.getLogger(__name__)


# Список слов, которые часто ошибочно распознаются из текста (артефакты)
COMMON_ARTIFACTS = {
    'по', 'и', 'в', 'во', 'на', 'не', 'к', 'со', 'со', 'за', 'с', 'у', 'он', 'она',
    'оно', 'они', 'это', 'так', 'что', 'как', 'а', 'б', 'г', 'д', 'е', 'ё', 'ж',
    'з', 'й', 'л', 'м', 'н', 'р', 'х', 'ц', 'ч', 'ш', 'щ', 'т', 'ъ', 'ь', 'э',
    'п', 'ф', 'б', 'ю', 'я', '—', '–', '-', '_',
    # Артефакты распознавания изображений (служебные слова)
    'мы', 'вы', 'ты', 'я', 'он', 'она', 'оно', 'они', 'вас', 'нас', 'вам', 'нам',
    'тот', 'эта', 'эти', 'того', 'той', 'того', 'том', 'той', 'той',
    'без', 'для', 'при', 'про', 'над', 'под', 'если', 'то', 'либо',
    'выход', 'выходных', 'доставк', 'ежедневно', 'часы', 'работ', 'работы',
    'магазин', 'инстаграм', 'одноклассник', 'фото', 'список', 'слов', 'слова',
    'картинка', 'изображение', 'фотография', 'текст', 'лист', 'страница',
    'примечание', 'примечания', 'прим', 'прим', 'изм', 'все', 'полностью'
}

# Символы, которые часто появляются в распознанном тексте как артефакты
ARTIFACTS_SYMBOLS = {',', '.', '!', '?', ':', ';', '(', ')', '[', ']', '{', '}', '"', "'", '/', '\\'}


def clean_word(word: str) -> str:
    """
    Очистить одно слово от артефактов и привести к стандартному виду
    
    Args:
        word: Исходное слово
        
    Returns:
        Очищенное слово (или пустая строка если невалидно)
    """
    if not word:
        return ""
    
    # Удаление пробелов в начале и конце
    word = word.strip()
    
    # Удаление символов, которые не должны быть в словах
    # Оставляем только русские буквы, дефис и мягкий/твёрдый знак
    word = re.sub(r'[^а-яёА-ЯЁ\-ъьЪЬ]', '', word)
    
    # Замена нескольких дефисов на один
    word = re.sub(r'-+', '-', word)
    
    # Удаление дефиса в начале и конце
    word = word.strip('-')
    
    # Приведение к нижнему регистру для унификации
    word = word.lower()
    
    return word


def validate_word(word: str) -> bool:
    """
    Проверить валидность слова для добавления в словарь
    
    Args:
        word: Слово для проверки
        
    Returns:
        True если слово валидно, False если нет
    """
    # Слово должно быть непусто после очистки
    if not word or len(word) < 2:
        return False
    
    # Слово не должно быть очень длинным (обычно словарные слова < 20 букв)
    if len(word) > 30:
        logger.debug(f"⚠️ Слово слишком длинное: {word} ({len(word)} букв)")
        return False
    
    # Слово должно содержать только русские буквы (и дефис/ъ/ь)
    if not re.match(r'^[а-яёъь\-]+$', word):
        logger.debug(f"⚠️ Слово содержит недопустимые символы: {word}")
        return False
    
    # Слово не должно быть одной повторяющейся буквой
    if len(set(word.replace('-', ''))) == 1:
        logger.debug(f"⚠️ Слово состоит из одной буквы: {word}")
        return False
    
    # Слово не в списке артефактов (частые ошибки распознавания)
    if word in COMMON_ARTIFACTS:
        logger.debug(f"⚠️ Слово - известный артефакт распознавания: {word}")
        return False
    
    return True


def clean_words_list(words: List[str]) -> List[str]:
    """
    Очистить список распознанных слов от дубликатов, артефактов и невалидных слов
    
    Args:
        words: Исходный список слов
        
    Returns:
        Очищенный список уникальных валидных слов
    """
    cleaned: Set[str] = set()
    
    for word in words:
        # Очистка слова
        cleaned_word = clean_word(word)
        
        # Проверка валидности
        if validate_word(cleaned_word):
            cleaned.add(cleaned_word)
    
    # Преобразование в список и сортировка
    result = sorted(list(cleaned))
    
    logger.info(f"📝 Список слов: {len(words)} → {len(result)} (очищено от дубликатов и артефактов)")
    
    # Проверка количества слов
    if len(result) > MAX_WORDS_IN_DICTIONARY:
        logger.warning(f"⚠️ Слов больше чем максимум ({len(result)} > {MAX_WORDS_IN_DICTIONARY})")
        result = result[:MAX_WORDS_IN_DICTIONARY]
        logger.info(f"✂️ Обрезано до {len(result)} слов")
    
    return result


def parse_recognized_text(text: str) -> List[str]:
    """
    Парсить текст, распознанный Vision API, в список слов
    
    Args:
        text: Текст с распознанными словами (одно слово на строку или через запятую)
        
    Returns:
        Список очищенных слов
    """
    # Разбиение по строкам и запятым
    lines = text.split('\n')
    words = []
    
    for line in lines:
        # Разбиение по запятым если есть несколько слов на одной строке
        for part in line.split(','):
            part = part.strip()
            if part:
                words.append(part)
    
    logger.info(f"🔍 Распарсено {len(words)} слов из распознанного текста")
    logger.debug(f"📋 Слова ДО очистки: {words}")
    
    # Очистка списка
    cleaned = clean_words_list(words)
    
    logger.info(f"✅ После фильтрации: {len(cleaned)} слов")
    logger.debug(f"📋 Слова ПОСЛЕ очистки: {cleaned}")
    
    return cleaned


def format_words_for_display(words: List[str]) -> str:
    """
    Форматировать список слов для показа пользователю
    
    Args:
        words: Список слов
        
    Returns:
        Отформатированная строка
    """
    if not words:
        return "❌ Нет слов для отображения"
    
    formatted = "📚 Распознанные слова:\n\n"
    for i, word in enumerate(words, 1):
        formatted += f"{i}. {word}\n"
    
    formatted += f"\n✅ Всего: {len(words)} слов"
    
    return formatted


def validate_words_count(words: List[str]) -> tuple[bool, str]:
    """
    Проверить количество слов (не пусто, не более максимума)
    
    Args:
        words: Список слов
        
    Returns:
        Кортеж (валиден, сообщение)
    """
    if not words:
        return False, "❌ Список слов пуст"
    
    if len(words) > MAX_WORDS_IN_DICTIONARY:
        return False, f"❌ Слишком много слов: {len(words)} (максимум {MAX_WORDS_IN_DICTIONARY})"
    
    if len(words) < 2:
        return False, "❌ Нужно минимум 2 слова"
    
    return True, f"✅ {len(words)} слов (в порядке)"
