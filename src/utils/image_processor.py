"""
Утилиты для обработки изображений перед отправкой в Vision API
"""

import base64
import logging
from io import BytesIO
from typing import Tuple

from PIL import Image, ImageEnhance, ImageOps

from config.settings import MAX_FILE_SIZE


logger = logging.getLogger(__name__)


def validate_image(image_bytes: bytes) -> Tuple[bool, str]:
    """
    Проверить валидность изображения (формат, размер)
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        Кортеж (валиден, сообщение об ошибке)
    """
    # Проверка размера файла
    if len(image_bytes) > MAX_FILE_SIZE:
        error_msg = f"❌ Файл слишком большой: {len(image_bytes) / (1024*1024):.1f} МБ (максимум {MAX_FILE_SIZE / (1024*1024):.0f} МБ)"
        logger.warning(error_msg)
        return False, error_msg
    
    # Проверка формата изображения
    try:
        image = Image.open(BytesIO(image_bytes))
        
        # Проверка поддерживаемых форматов
        if image.format not in ['JPEG', 'PNG', 'GIF', 'WEBP']:
            error_msg = f"❌ Неподдерживаемый формат: {image.format}. Используйте JPEG, PNG, GIF или WebP"
            logger.warning(error_msg)
            return False, error_msg
        
        # Базовая проверка - изображение загружается без ошибок
        image.verify()
        logger.info(f"✅ Изображение валидно: {image.format} ({image.width}x{image.height})")
        return True, ""
    
    except Exception as e:
        error_msg = f"❌ Ошибка при проверке изображения: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def preprocess_image(image_bytes: bytes, max_width: int = 2048) -> bytes:
    """
    Предобработка изображения для улучшения качества распознавания текста:
    - Улучшение контраста
    - Преобразование в RGB при необходимости
    - Оптимизация размера
    
    Args:
        image_bytes: Исходные байты изображения
        max_width: Максимальная ширина изображения
        
    Returns:
        Предобработанные байты изображения
    """
    try:
        # Открытие изображения
        image = Image.open(BytesIO(image_bytes))
        logger.debug(f"📸 Исходное изображение: {image.format} {image.size}")
        
        # Преобразование в RGB если нужно (для PNG с альфа-каналом и т.д.)
        if image.mode in ['RGBA', 'LA', 'P']:
            # Создание белого фона для прозрачности
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ['RGBA', 'LA'] else None)
            image = background
            logger.debug("🎨 Преобразовано в RGB")
        elif image.mode != 'RGB':
            image = image.convert('RGB')
            logger.debug(f"🎨 Преобразовано в RGB (было {image.mode})")
        
        # Оптимизация размера - не больше max_width
        if image.width > max_width:
            ratio = max_width / image.width
            new_height = int(image.height * ratio)
            image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"📏 Изображение уменьшено до {image.size}")
        
        # Улучшение контраста для лучшего распознавания текста
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.3)  # Увеличиваем контраст на 30%
        logger.debug("📊 Контраст повышен на 30%")
        
        # Улучшение резкости
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.2)  # Увеличиваем резкость на 20%
        logger.debug("✂️ Резкость повышена на 20%")
        
        # Сохранение в JPEG (хороший компромисс между качеством и размером)
        output = BytesIO()
        image.save(output, format='JPEG', quality=90, optimize=True)
        output_bytes = output.getvalue()
        
        logger.info(f"✅ Предобработка завершена: {len(image_bytes)} → {len(output_bytes)} байт")
        return output_bytes
    
    except Exception as e:
        logger.error(f"❌ Ошибка при предобработке изображения: {e}")
        logger.info("⚠️ Возвращаем исходное изображение")
        return image_bytes


def convert_to_base64(image_bytes: bytes) -> str:
    """
    Конвертировать байты изображения в base64 для передачи в API
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        Base64-кодированная строка изображения
    """
    try:
        base64_str = base64.b64encode(image_bytes).decode('utf-8')
        logger.debug(f"🔐 Изображение закодировано в base64 ({len(base64_str)} символов)")
        return base64_str
    except Exception as e:
        logger.error(f"❌ Ошибка при кодировании в base64: {e}")
        raise ValueError(f"Не удалось закодировать изображение: {e}")


def resize_image(image_bytes: bytes, max_width: int = 1024, max_height: int = 1024) -> bytes:
    """
    Простое уменьшение размера изображения с сохранением пропорций
    
    Args:
        image_bytes: Байты изображения
        max_width: Максимальная ширина
        max_height: Максимальная высота
        
    Returns:
        Уменьшенные байты изображения
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        output = BytesIO()
        image.save(output, format='JPEG', quality=90)
        return output.getvalue()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при изменении размера: {e}")
        return image_bytes
