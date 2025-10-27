"""
Тестовый handler для проверки TTS функциональности
Временный файл для демонстрации работы генерации аудио
"""

import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

from src.services.tts_service import TTSService

logger = logging.getLogger(__name__)
router = Router()

# Глобальные переменные для сервисов (инициализируются в main.py)
tts_service: TTSService = None


def init_tts_test_handler(tts_svc: TTSService):
    """Инициализация handler с сервисом TTS"""
    global tts_service
    tts_service = tts_svc
    logger.info("✅ TTS test handler инициализирован")


@router.message(Command("test_tts"))
async def cmd_test_tts(message: types.Message):
    """
    Команда для тестирования TTS функциональности
    
    Использование: /test_tts корова
    Генерирует аудио для слова "корова"
    """
    if not tts_service:
        await message.answer("❌ TTS сервис не инициализирован!")
        return
    
    # Получение слова из аргументов команды
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "🎤 Тестирование TTS (Text-to-Speech)\n\n"
            "Использование: /test_tts <слово>\n\n"
            "Пример: /test_tts корова\n\n"
            "Бот сгенерирует аудио произношения слова и отправит его вам."
        )
        return
    
    word = args[1].strip()
    
    if not word or len(word) > 50:
        await message.answer("❌ Слово должно быть от 1 до 50 символов!")
        return
    
    # Показываем статус
    status_msg = await message.answer(f"🔊 Генерируем аудио для слова '{word}'...")
    
    try:
        # Генерация аудио
        audio_bytes = await tts_service.generate_audio(word)
        
        if audio_bytes is None:
            await status_msg.edit_text(f"❌ Ошибка при генерации аудио для слова '{word}'")
            return
        
        # Отправка аудио
        await message.answer_voice(
            voice=types.input_file.BufferedInputFile(
                file=audio_bytes,
                filename=f"{word}.mp3"
            ),
            caption=f"🎵 Произношение слова: **{word}**"
        )
        
        # Удаление статуса
        await status_msg.delete()
        
        logger.info(f"✅ Аудио для '{word}' успешно отправлено")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации аудио: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


@router.message(Command("tts_cache_info"))
async def cmd_tts_cache_info(message: types.Message):
    """
    Информация о TTS кэше
    """
    if not tts_service:
        await message.answer("❌ TTS сервис не инициализирован!")
        return
    
    cache_info = tts_service.get_cache_info()
    
    info_text = (
        "📊 Информация о кэше аудио:\n\n"
        f"📁 Папка: `{cache_info.get('cache_dir', 'N/A')}`\n"
        f"📦 Файлов: {cache_info.get('total_files', 0)}\n"
        f"💾 Размер: {cache_info.get('total_size_mb', 0)} МБ"
    )
    
    await message.answer(info_text)
    logger.info(f"Cache info: {cache_info}")


@router.message(Command("clear_tts_cache"))
async def cmd_clear_tts_cache(message: types.Message):
    """
    Команда для очистки кэша аудио
    """
    if not tts_service:
        await message.answer("❌ TTS сервис не инициализирован!")
        return
    
    try:
        tts_service.clear_cache()
        await message.answer("✅ Кэш аудио успешно очищен!")
        logger.info("Кэш аудио успешно очищен")
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке кэша аудио: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")