"""
Обработчики Telegram бота
"""

from aiogram import Router
from .start_handler import router as start_router
from .photo_handler import router as photo_router
from .dictionary_handler import router as dictionary_router
from .learning_handler import router as learning_router
from .progress_handler import router as progress_router
from .tts_test_handler import router as tts_test_router

# Комбинированный router со всеми обработчиками
router = Router()
# ВАЖНО: Команды и более специфичные роутеры ПЕРВЫМИ
# Затем общие обработчики F.text в конце
router.include_router(start_router)      # Команды: /start, /help, /menu (Command фильтр имеет приоритет)
router.include_router(progress_router)   # Обработчик прогресса
router.include_router(tts_test_router)   # TTS команды
router.include_router(learning_router)   # Обработчик сессии обучения
router.include_router(photo_router)      # Фото обработчик
router.include_router(dictionary_router)  # Редактирование (F.text ловушка - ПОСЛЕДНИЙ)

__all__ = ["router"]
