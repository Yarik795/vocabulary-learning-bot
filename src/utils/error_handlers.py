"""
Обработчики ошибок и fallback механизмы для всех API (Этап 8)
Включает обработку Vision API, TTS API, LLM ошибок и edge cases
"""

import logging
from typing import Optional, List
import asyncio

logger = logging.getLogger(__name__)


class APIErrorHandler:
    """Обработчик ошибок API с fallback механизмами"""
    
    @staticmethod
    async def handle_vision_error(error: Exception, context: dict = None) -> dict:
        """
        Обработка ошибок Vision API (распознавание текста)
        
        Args:
            error: Exception из Vision Service
            context: Контекст ошибки (например, размер фото)
            
        Returns:
            Словарь с сообщением об ошибке для пользователя
        """
        error_str = str(error).lower()
        logger.error(f"❌ Vision API ошибка: {error}")
        
        # Классификация ошибок
        if "timeout" in error_str or "request timeout" in error_str:
            return {
                'user_message': """❌ **Тайм-аут при распознавании текста**

Сервис распознавания временно перегружен. 

**Что сделать:**
1️⃣ Попробуй загрузить фото снова через 10 секунд
2️⃣ Убедись что фото чёткое и хорошо освещено
3️⃣ Если ошибка повторяется, попробуй в другом словаре""",
                'error_code': 'VISION_TIMEOUT',
                'retry_allowed': True
            }
        
        elif "invalid" in error_str or "bad request" in error_str or "400" in error_str:
            return {
                'user_message': """❌ **Фотография не соответствует требованиям**

**Требования к фото:**
✅ Чёткий текст на белом/светлом фоне
✅ Хороший размер шрифта (не меньше 12pt)
✅ Естественное освещение (без теней)
✅ Размер файла меньше 10MB
❌ Не подходят: размытые, косые, тёмные фото

**Совет:** Используй встроенную камеру, а не скриншот!""",
                'error_code': 'VISION_INVALID_IMAGE',
                'retry_allowed': True
            }
        
        elif "429" in error_str or "rate limit" in error_str:
            return {
                'user_message': """⏳ **Слишком много запросов**

Ты отправляешь фото слишком часто. 

**Подожди 30 секунд и попробуй снова** ⏰""",
                'error_code': 'VISION_RATE_LIMIT',
                'retry_allowed': True,
                'retry_delay': 30
            }
        
        else:
            return {
                'user_message': """❌ **Ошибка распознавания текста**

Что-то пошло не так при обработке фото. 

**Попробуй:**
1️⃣ Переделать фото в лучшем освещении
2️⃣ Отправить файл меньшего размера
3️⃣ Если проблема в сервисе - подожди и попробуй позже""",
                'error_code': 'VISION_UNKNOWN',
                'retry_allowed': True
            }
    
    @staticmethod
    async def handle_tts_error(word: str, error: Exception) -> dict:
        """
        Обработка ошибок TTS API (генерация аудио)
        
        Args:
            word: Слово для которого не удалось сгенерировать аудио
            error: Exception из TTS Service
            
        Returns:
            Словарь с информацией о fallback
        """
        error_str = str(error).lower()
        logger.error(f"❌ TTS API ошибка для слова '{word}': {error}")
        
        if "timeout" in error_str:
            return {
                'user_message': f"🔊 Аудио для '{word}' генерируется... (может быть без звука)",
                'error_code': 'TTS_TIMEOUT',
                'fallback_action': 'show_word_without_audio'
            }
        
        elif "429" in error_str or "rate limit" in error_str:
            return {
                'user_message': f"🔊 Временно нет доступа к аудио для '{word}'",
                'error_code': 'TTS_RATE_LIMIT',
                'fallback_action': 'show_word_without_audio'
            }
        
        else:
            return {
                'user_message': f"🔊 Не удалось загрузить аудио для '{word}' (продолжаем без звука)",
                'error_code': 'TTS_UNKNOWN',
                'fallback_action': 'show_word_without_audio'
            }
    
    @staticmethod
    async def handle_variant_generation_error(words: List[str], error: Exception) -> dict:
        """
        Обработка ошибок при генерации вариантов (LLM API)
        
        Args:
            words: Список слов для которых не удалась генерация
            error: Exception из Variant Generator Service
            
        Returns:
            Словарь с информацией о fallback
        """
        error_str = str(error).lower()
        word_count = len(words) if isinstance(words, list) else 1
        logger.error(f"❌ Ошибка генерации вариантов для {word_count} слов: {error}")
        
        if "timeout" in error_str:
            return {
                'user_message': f"⏳ Генерируем варианты... (может занять время)",
                'error_code': 'VARIANT_TIMEOUT',
                'fallback_action': 'use_cached_or_algorithmic',
                'retry_allowed': True,
                'retry_delay': 5
            }
        
        elif "429" in error_str or "rate limit" in error_str:
            return {
                'user_message': f"⏳ Слишком много запросов, подожди...",
                'error_code': 'VARIANT_RATE_LIMIT',
                'fallback_action': 'use_cached_or_algorithmic',
                'retry_allowed': True,
                'retry_delay': 10
            }
        
        elif "invalid" in error_str or "parse" in error_str:
            return {
                'user_message': f"⚙️ Переформатируем варианты...",
                'error_code': 'VARIANT_PARSE_ERROR',
                'fallback_action': 'use_algorithmic_generation'
            }
        
        else:
            return {
                'user_message': f"⚙️ Подготавливаем варианты альтернативным способом...",
                'error_code': 'VARIANT_UNKNOWN',
                'fallback_action': 'use_algorithmic_generation'
            }


class ImageValidator:
    """Валидация изображений для обработки"""
    
    @staticmethod
    def validate_image_size(file_size_bytes: int, max_size_mb: int = 10) -> tuple[bool, Optional[str]]:
        """
        Проверка размера изображения
        
        Args:
            file_size_bytes: Размер файла в байтах
            max_size_mb: Максимальный размер в МБ
            
        Returns:
            Кортеж (валидно ли, сообщение об ошибке)
        """
        max_bytes = max_size_mb * 1024 * 1024
        
        if file_size_bytes > max_bytes:
            size_mb = file_size_bytes / (1024 * 1024)
            return False, f"❌ Фото слишком большое ({size_mb:.1f}MB, максимум {max_size_mb}MB)"
        
        if file_size_bytes < 1024:  # Меньше 1KB
            return False, "❌ Фото слишком маленькое (может быть повреждено)"
        
        return True, None
    
    @staticmethod
    def validate_image_content(width: int, height: int, min_size: int = 100) -> tuple[bool, Optional[str]]:
        """
        Проверка разрешения изображения
        
        Args:
            width: Ширина в пикселях
            height: Высота в пикселях
            min_size: Минимальное разрешение
            
        Returns:
            Кортеж (валидно ли, сообщение об ошибке)
        """
        if width < min_size or height < min_size:
            return False, f"❌ Фото слишком низкого разрешения ({width}x{height}, нужно минимум {min_size}x{min_size})"
        
        return True, None
    
    @staticmethod
    def validate_file_type(mime_type: str) -> tuple[bool, Optional[str]]:
        """
        Проверка типа файла
        
        Args:
            mime_type: MIME тип файла
            
        Returns:
            Кортеж (валидно ли, сообщение об ошибке)
        """
        allowed_types = ['image/jpeg', 'image/png', 'image/webp']
        
        if mime_type not in allowed_types:
            return False, f"❌ Неподдерживаемый формат ({mime_type}). Используй JPEG, PNG или WebP"
        
        return True, None


class EdgeCaseHandler:
    """Обработчик граничных случаев"""
    
    @staticmethod
    def validate_words_count(words: List[str], max_words: int = 50, min_words: int = 1) -> tuple[bool, Optional[str]]:
        """
        Проверка количества слов в словаре
        
        Args:
            words: Список слов
            max_words: Максимальное количество слов
            min_words: Минимальное количество слов
            
        Returns:
            Кортеж (валидно ли, сообщение об ошибке)
        """
        word_count = len(words)
        
        if word_count < min_words:
            return False, f"❌ Недостаточно слов ({word_count}, нужно минимум {min_words})"
        
        if word_count > max_words:
            return False, f"⚠️ Слишком много слов ({word_count}, максимум {max_words})"
        
        return True, None
    
    @staticmethod
    def validate_word_content(word: str) -> tuple[bool, Optional[str]]:
        """
        Проверка содержимого слова
        
        Args:
            word: Слово для проверки
            
        Returns:
            Кортеж (валидно ли, сообщение об ошибке)
        """
        if not word or len(word.strip()) == 0:
            return False, "❌ Пустое слово"
        
        if len(word) > 50:
            return False, "❌ Слово слишком длинное (максимум 50 символов)"
        
        if len(word) < 2:
            return False, "❌ Слово слишком короткое (минимум 2 символа)"
        
        return True, None


def get_user_friendly_error_message(error_code: str, context: dict = None) -> str:
    """
    Получить пользовательское сообщение об ошибке по коду
    
    Args:
        error_code: Код ошибки (например, 'VISION_TIMEOUT')
        context: Контекст ошибки
        
    Returns:
        Сообщение для пользователя
    """
    messages = {
        'VISION_TIMEOUT': "⏳ Распознавание занимает дольше обычного. Пожалуйста, подожди...",
        'VISION_INVALID_IMAGE': "📸 Фото не читается. Попробуй загрузить более чёткую фотографию.",
        'VISION_RATE_LIMIT': "⚡ Слишком много запросов. Подожди немного перед следующей попыткой.",
        'TTS_TIMEOUT': "🔊 Звук генерируется... Продолжаем без аудио.",
        'TTS_RATE_LIMIT': "⏳ Временно нет доступа к звуку. Продолжаем учить слова.",
        'VARIANT_TIMEOUT': "⚙️ Варианты генерируются дольше обычного...",
        'VARIANT_RATE_LIMIT': "⏳ API перегружен, подожди и попробуй снова.",
        'VARIANT_PARSE_ERROR': "⚙️ Переформатируем данные...",
        'VARIANT_UNKNOWN': "⚙️ Подготавливаем варианты...",
    }
    
    return messages.get(error_code, "❌ Произошла ошибка. Попробуй ещё раз.")
