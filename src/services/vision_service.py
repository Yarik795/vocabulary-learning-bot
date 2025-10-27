"""
Сервис распознавания текста с изображений через Vision API
"""

import logging
from typing import List

from config.prompts import VISION_PROMPT
from src.utils.image_processor import validate_image, preprocess_image, convert_to_base64
from src.utils.validators import parse_recognized_text
from src.services.openrouter_client import OpenRouterClient


logger = logging.getLogger(__name__)


class VisionService:
    """
    Сервис распознавания текста с изображений через OpenRouter Vision API
    """
    
    def __init__(self):
        """Инициализация сервиса Vision"""
        logger.info("👁️ Инициализация VisionService...")
        try:
            self.client = OpenRouterClient()
            logger.info("👁️ VisionService инициализирован успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации VisionService: {e}")
            raise
    
    async def recognize_text(self, image_bytes: bytes) -> List[str]:
        """
        Распознать текст с изображения и вернуть список слов
        
        Args:
            image_bytes: Байты изображения
            
        Returns:
            Список распознанных слов
            
        Raises:
            ValueError: При ошибке валидации или распознавания
        """
        logger.info("📸 Начало распознавания текста с изображения...")
        
        # 1. Валидация изображения
        is_valid, error_msg = validate_image(image_bytes)
        if not is_valid:
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 2. Предобработка изображения (улучшение контраста, размер и т.д.)
        logger.debug("🔧 Предобработка изображения...")
        processed_image = preprocess_image(image_bytes)
        
        # 3. Конвертация в base64 для API
        logger.debug("🔐 Конвертация в base64...")
        image_base64 = convert_to_base64(processed_image)
        
        # 4. Отправка запроса к Vision API
        logger.info("📤 Отправка запроса к Vision API...")
        try:
            response_text = await self.client.vision_request(
                image_base64=image_base64,
                prompt=VISION_PROMPT
            )
            logger.info(f"📥 Ответ получен ({len(response_text)} символов)")
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе к Vision API: {e}")
            raise ValueError(f"Ошибка распознавания текста: {e}")
        
        # 5. Парсинг и очистка распознанного текста
        logger.debug("🔍 Парсинг распознанного текста...")
        logger.info(f"📝 Исходный ответ Vision API:\n{response_text}")
        words = parse_recognized_text(response_text)
        
        if not words:
            logger.warning("⚠️ Слова не распознаны из изображения")
            raise ValueError("❌ Не удалось распознать слова с изображения. Попробуйте загрузить чёткое фото со списком слов.")
        
        logger.info(f"✅ Распознавание завершено: {len(words)} слов")
        logger.debug(f"Слова: {words}")
        
        return words
    
    async def recognize_text_with_fallback(self, image_bytes: bytes, max_retries: int = 2) -> List[str]:
        """
        Распознать текст с повторными попытками при ошибке
        
        Args:
            image_bytes: Байты изображения
            max_retries: Максимальное количество попыток
            
        Returns:
            Список распознанных слов
            
        Raises:
            ValueError: Если не удалось распознать даже после повторных попыток
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Попытка распознавания {attempt + 1}/{max_retries}...")
                words = await self.recognize_text(image_bytes)
                return words
            except ValueError as e:
                logger.warning(f"⚠️ Попытка {attempt + 1} не удалась: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"❌ Не удалось распознать после {max_retries} попыток")
                    raise
        
        raise ValueError("❌ Не удалось распознать текст с изображения")
