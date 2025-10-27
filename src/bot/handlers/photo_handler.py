"""
Обработчик фотографий: приём и распознавание текста
"""

import logging
from io import BytesIO
from typing import Dict, Any

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

from src.services.vision_service import VisionService
from src.utils.validators import format_words_for_display, validate_words_count
from src.utils.file_helpers import save_user_session, load_user_session, delete_user_session
from src.services.tts_service import TTSService
from src.utils.error_handlers import APIErrorHandler, ImageValidator, EdgeCaseHandler


logger = logging.getLogger(__name__)

router = Router(name="photo_router")

logger.info("✅ Router фото инициализирован")


# ============================================================================
# ОБРАБОТЧИК ФОТОГРАФИЙ (как PHOTO)
# ============================================================================

@router.message(F.photo)
async def handle_photo(message: types.Message):
    """
    Обработчик загруженных фотографий со словами
    """
    user_id = message.from_user.id
    logger.info(f"📸 PHOTO HANDLER TRIGGERED! Пользователь {user_id} загрузил фото (файл получен)")
    
    # Сообщение о начале обработки
    try:
        processing_msg = await message.answer("🔍 Распознаю слова...")
        logger.debug(f"✅ Отправлено сообщение 'Распознаю...'")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения: {e}")
        processing_msg = None
    
    try:
        # Получение информации о фотографии (файл с наибольшим разрешением)
        photo = message.photo[-1]
        logger.debug(f"📷 Получена информация о фото: file_id={photo.file_id}")
        
        file_info = await message.bot.get_file(photo.file_id)
        logger.debug(f"📥 Информация о файле получена: размер={file_info.file_size} байт, путь={file_info.file_path}")
        
        # Скачивание файла
        logger.debug(f"📥 Скачивание фото ({file_info.file_size} байт)...")
        file_bytesio = await message.bot.download_file(file_info.file_path)
        
        # Чтение в BytesIO
        image_bytes = file_bytesio.getvalue() if hasattr(file_bytesio, 'getvalue') else file_bytesio
        logger.debug(f"✅ Фото скачано ({len(image_bytes)} байт)")
        
        # === ПРОВЕРКА РАЗМЕРА ФАЙЛА (Этап 8) ===
        is_valid, error_msg = ImageValidator.validate_image_size(len(image_bytes), max_size_mb=10)
        if not is_valid:
            if processing_msg:
                await processing_msg.delete()
            await message.answer(error_msg)
            return
        
        # Инициализация Vision сервиса
        vision_service = VisionService()
        
        # Распознавание текста
        logger.info("🔄 Запуск распознавания...")
        words = await vision_service.recognize_text(image_bytes)
        
        # === КАПИТАЛИЗАЦИЯ ПЕРВЫХ БУКВ СЛОВ ===
        words = [word.capitalize() if word else word for word in words]
        logger.debug(f"✅ Слова капитализированы")
        
        # === ПРОВЕРКА КОЛИЧЕСТВА СЛОВ (Этап 8) ===
        is_valid, error_msg = EdgeCaseHandler.validate_words_count(words, max_words=50, min_words=1)
        if not is_valid:
            if processing_msg:
                await processing_msg.delete()
            await message.answer(
                error_msg + "\n\n"
                "📝 **Рекомендация:**\n"
                "Создай несколько словарей вместо одного большого словаря.\n"
                "Это поможет лучше учить слова! 📚"
            , parse_mode="Markdown")
            return
        
        # Сохранение слов в сессию пользователя (в JSON файл)
        session_data: Dict[str, Any] = {"words": words}
        if save_user_session(user_id, session_data):
            logger.info(f"💾 Слова сохранены в сессию пользователя {user_id}")
        else:
            logger.warning(f"⚠️ Ошибка при сохранении сессии пользователя {user_id}")
        
        # Форматирование для показа
        display_text = format_words_for_display(words)
        
        # Кнопки для редактирования
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="words_confirm")
            ]
        ])
        
        # Удаление сообщения "Распознаю..."
        if processing_msg:
            await processing_msg.delete()
            logger.debug(f"✅ Удалено сообщение 'Распознаю...'")
        
        # Отправка результата
        await message.answer(display_text, reply_markup=keyboard)
        logger.info(f"✅ Результаты отправлены пользователю {user_id}")
        
    except ValueError as e:
        # Ошибки валидации изображения или распознавания
        logger.error(f"❌ Ошибка валидации: {e}")
        if processing_msg:
            await processing_msg.delete()
            logger.debug(f"✅ Удалено сообщение 'Распознаю...'")
        
        error_text = str(e)
        if "❌" not in error_text:
            error_text = f"❌ {error_text}"
        
        await message.answer(
            error_text + "\n\n"
            "💡 Попробуйте:\n"
            "• Загрузить чёткое фото\n"
            "• Лучше освещение\n"
            "• Фото со списком слов (не с картинками)",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при обработке фото: {e}", exc_info=True)
        if processing_msg:
            await processing_msg.delete()
            logger.debug(f"✅ Удалено сообщение 'Распознаю...'")
        
        await message.answer(
            "❌ Ошибка при распознавании текста.\n\n"
            "Попробуйте:\n"
            "• Загрузить другое фото\n"
            "• Проверить подключение к интернету"
        )


# ============================================================================
# ОБРАБОТЧИК ДОКУМЕНТОВ - ИЗОБРАЖЕНИЙ (как DOCUMENT)
# ============================================================================

@router.message(F.document)
async def handle_document(message: types.Message):
    """
    Обработчик документов (включая изображения, отправленные как документы)
    """
    user_id = message.from_user.id
    
    # Проверяем, является ли документ изображением
    mime_type = message.document.mime_type if message.document else None
    logger.info(f"📄 DOCUMENT получен от {user_id}, mime_type: {mime_type}")
    
    # Если это изображение (JPEG, PNG, WebP и т.д.)
    if mime_type and mime_type.startswith("image/"):
        logger.info(f"🖼️ Это изображение! Обработаю как фото...")
        
        # Обработаем как фото
        await handle_photo_from_document(message)
    else:
        logger.warning(f"❌ Документ не является изображением: {mime_type}")
        await message.answer(
            "❌ Это не изображение!\n\n"
            "Пожалуйста, отправьте фотографию со списком слов (JPG, PNG и т.д.)"
        )


async def handle_photo_from_document(message: types.Message):
    """
    Обработчик фотографии, пришедшей как документ
    """
    user_id = message.from_user.id
    logger.info(f"📸 PHOTO FROM DOCUMENT HANDLER TRIGGERED! Пользователь {user_id} загрузил фото как документ")
    
    # Сообщение о начале обработки
    try:
        processing_msg = await message.answer("🔍 Распознаю слова...")
        logger.debug(f"✅ Отправлено сообщение 'Распознаю...'")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения: {e}")
        processing_msg = None
    
    try:
        # Получение информации о фотографии (файл с наибольшим разрешением)
        photo = message.document
        logger.debug(f"📷 Получена информация о фото: file_id={photo.file_id}")
        
        file_info = await message.bot.get_file(photo.file_id)
        logger.debug(f"📥 Информация о файле получена: размер={file_info.file_size} байт, путь={file_info.file_path}")
        
        # Скачивание файла
        logger.debug(f"📥 Скачивание фото ({file_info.file_size} байт)...")
        file_bytesio = await message.bot.download_file(file_info.file_path)
        
        # Чтение в BytesIO
        image_bytes = file_bytesio.getvalue() if hasattr(file_bytesio, 'getvalue') else file_bytesio
        logger.debug(f"✅ Фото скачано ({len(image_bytes)} байт)")
        
        # === ПРОВЕРКА РАЗМЕРА ФАЙЛА (Этап 8) ===
        is_valid, error_msg = ImageValidator.validate_image_size(len(image_bytes), max_size_mb=10)
        if not is_valid:
            if processing_msg:
                await processing_msg.delete()
            await message.answer(error_msg)
            return
        
        # Инициализация Vision сервиса
        vision_service = VisionService()
        
        # Распознавание текста
        logger.info("🔄 Запуск распознавания...")
        words = await vision_service.recognize_text(image_bytes)
        
        # === КАПИТАЛИЗАЦИЯ ПЕРВЫХ БУКВ СЛОВ ===
        words = [word.capitalize() if word else word for word in words]
        logger.debug(f"✅ Слова капитализированы")
        
        # === ПРОВЕРКА КОЛИЧЕСТВА СЛОВ (Этап 8) ===
        is_valid, error_msg = EdgeCaseHandler.validate_words_count(words, max_words=50, min_words=1)
        if not is_valid:
            if processing_msg:
                await processing_msg.delete()
            await message.answer(
                error_msg + "\n\n"
                "📝 **Рекомендация:**\n"
                "Создай несколько словарей вместо одного большого словаря.\n"
                "Это поможет лучше учить слова! 📚"
            , parse_mode="Markdown")
            return
        
        # Сохранение слов в сессию пользователя (в JSON файл)
        session_data: Dict[str, Any] = {"words": words}
        if save_user_session(user_id, session_data):
            logger.info(f"💾 Слова сохранены в сессию пользователя {user_id}")
        else:
            logger.warning(f"⚠️ Ошибка при сохранении сессии пользователя {user_id}")
        
        # Форматирование для показа
        display_text = format_words_for_display(words)
        
        # Кнопки для редактирования
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="words_confirm")
            ]
        ])
        
        # Удаление сообщения "Распознаю..."
        if processing_msg:
            await processing_msg.delete()
            logger.debug(f"✅ Удалено сообщение 'Распознаю...'")
        
        # Отправка результата
        await message.answer(display_text, reply_markup=keyboard)
        logger.info(f"✅ Результаты отправлены пользователю {user_id}")
        
    except ValueError as e:
        # Ошибки валидации изображения или распознавания
        logger.error(f"❌ Ошибка валидации: {e}")
        if processing_msg:
            await processing_msg.delete()
            logger.debug(f"✅ Удалено сообщение 'Распознаю...'")
        
        error_text = str(e)
        if "❌" not in error_text:
            error_text = f"❌ {error_text}"
        
        await message.answer(
            error_text + "\n\n"
            "💡 Попробуйте:\n"
            "• Загрузить чёткое фото\n"
            "• Лучше освещение\n"
            "• Фото со списком слов (не с картинками)",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при обработке фото: {e}", exc_info=True)
        if processing_msg:
            await processing_msg.delete()
            logger.debug(f"✅ Удалено сообщение 'Распознаю...'")
        
        await message.answer(
            "❌ Ошибка при распознавании текста.\n\n"
            "Попробуйте:\n"
            "• Загрузить другое фото\n"
            "• Проверить подключение к интернету"
        )


# ============================================================================
# ОБРАБОТЧИК КНОПКИ "ГОТОВО"
# ============================================================================

@router.callback_query(F.data == "words_confirm")
async def confirm_words(callback: types.CallbackQuery):
    """
    Подтверждение списка слов (кнопка "Готово")
    Интегрирует batch-генерацию вариантов
    """
    user_id = callback.from_user.id
    logger.info(f"👤 Пользователь {user_id} подтвердил список слов")
    
    # Получение слов из сессии (из JSON файла)
    session_data = load_user_session(user_id)
    if session_data is None:
        await callback.answer("❌ Сессия истекла. Загрузите фото ещё раз.", show_alert=True)
        return
    
    words = session_data.get("words", [])
    
    # Валидация
    is_valid, msg = validate_words_count(words)
    if not is_valid:
        await callback.answer(msg, show_alert=True)
        return
    
    # Показываем статус
    await callback.message.edit_text(
        f"✅ <b>Словарь принят!</b>\n\n"
        f"📚 Слов: {len(words)}\n"
        f"📝 Первые 3: {', '.join(words[:3])}\n\n"
        f"⏳ Подготавливаю варианты для {len(words)} слов...",
        parse_mode="HTML"
    )
    
    try:
        # === ЭТАП 2: BATCH-ГЕНЕРАЦИЯ ВАРИАНТОВ ===
        from src.services.variant_generator_service import VariantGeneratorService
        from src.core.dictionary_manager import DictionaryManager
        
        logger.info(f"🔄 Запуск batch-генерации вариантов для пользователя {user_id}...")
        variant_generator = VariantGeneratorService()
        
        # Batch-генерация для всех слов
        all_variants = await variant_generator.generate_variants_batch(words)
        
        # Проверяем результат
        if not all_variants:
            logger.error(f"❌ Batch-генерация не дала результатов")
            await callback.message.edit_text(
                "❌ Ошибка при подготовке вариантов.\n\n"
                "Попробуйте загрузить фото ещё раз."
            )
            return
        
        # Проверяем что все слова получили варианты
        missing_variants = [w for w in words if w not in all_variants]
        success_count = len(all_variants)
        
        if missing_variants:
            logger.warning(f"⚠️ Для {len(missing_variants)} слов не удалось сгенерировать варианты: {missing_variants}")
            # Показываем предупреждение но продолжаем
            await callback.answer(
                f"⚠️ Для {len(missing_variants)} слов не удалось подготовить варианты. "
                f"Обучение будет доступно только для {success_count} слов.",
                show_alert=False
            )
        
        logger.info(f"✅ Batch-генерация успешна! Получены варианты для {success_count} слов")
        
        # === ЭТАП 3: BATCH-ГЕНЕРАЦИЯ АУДИО ===
        tts_service = TTSService()
        logger.info(f"🔄 Запуск batch-генерации аудио для {len(words)} слов...")
        
        try:
            audio_results = await tts_service.batch_generate_audio(words)
            
            # Подсчитываем успешно сгенерированные аудио
            successful_audio = sum(1 for word in words if word in audio_results and audio_results[word] is not None)
            failed_audio = len(words) - successful_audio
            
            if successful_audio > 0:
                if failed_audio > 0:
                    logger.warning(f"⚠️ Сгенерировано аудио для {successful_audio}/{len(words)} слов (ошибки: {failed_audio})")
                else:
                    logger.info(f"✅ Batch-генерация аудио успешна! Все {len(words)} слов готовы")
            else:
                logger.warning(f"⚠️ Не удалось сгенерировать аудио ни для одного слова, продолжаем без аудио")
        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при batch-генерации аудио: {e}. Продолжаем без аудио")
        
        # === ЭТАП 4: СОЗДАНИЕ СЛОВАРЯ В МЕНЕДЖЕРЕ ===
        dict_manager = DictionaryManager()
        dictionary = dict_manager.create_dictionary(
            user_id=user_id,
            words=words
        )
        
        if not dictionary:
            logger.error(f"❌ Ошибка при создании словаря в менеджере")
            await callback.message.edit_text(
                "❌ Ошибка при сохранении словаря.\n\n"
                "Попробуйте загрузить фото ещё раз."
            )
            return
        
        logger.info(f"✅ Словарь создан: ID {dictionary.id}, название: {dictionary.name}")
        
        # Сохраняем в сессию информацию о словаре
        session_data["variants_generated"] = True
        session_data["variants_count"] = success_count
        session_data["dictionary_id"] = dictionary.id
        session_data["dictionary_name"] = dictionary.name
        save_user_session(user_id, session_data)
        
        # Показываем успех
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        await callback.message.edit_text(
            f"✅ <b>Готово! Словарь создан</b>\n\n"
            f"📚 {dictionary.name}\n"
            f"📝 Всего слов: {len(words)}\n"
            f"✨ Варианты подготовлены: {success_count}/{len(words)}\n\n"
            f"🎓 Можно начинать обучение!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📚 К списку словарей", callback_data="view_dictionaries"),
                    InlineKeyboardButton(text="🎓 Начать обучение", callback_data=f"learning_start:{dictionary.id}")
                ]
            ])
        )
        
        # Очистка сессии после создания словаря
        delete_user_session(user_id)
        logger.info(f"🗑️ Сессия пользователя {user_id} очищена после создания словаря")
        
        logger.info(f"✅ Процесс подтверждения завершён для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при batch-генерации для пользователя {user_id}: {e}", exc_info=True)
        
        await callback.message.edit_text(
            "❌ Ошибка при подготовке словаря.\n\n"
            "Попробуйте загрузить фото ещё раз."
        )
    
    await callback.answer("✅ Готово!")


# ============================================================================
# ОБРАБОТЧИК КНОПКИ "РЕДАКТИРОВАТЬ"
# ============================================================================

@router.callback_query(F.data == "words_edit")
async def edit_words(callback: types.CallbackQuery):
    """
    Переход в режим редактирования слов
    """
    user_id = callback.from_user.id
    logger.info(f"👤 Пользователь {user_id} начал редактирование слов")
    
    # Получение слов из сессии (из JSON файла)
    session_data = load_user_session(user_id)
    if session_data is None:
        await callback.answer("❌ Сессия истекла.", show_alert=True)
        return
    
    words = session_data.get("words", [])
    
    # Форматирование списка с номерами для удаления
    words_text = "✏️ <b>Редактирование списка</b>\n\n"
    words_text += "Отправьте слова через запятую или новую строку:\n"
    words_text += "(сейчас: " + ", ".join(words[:5])
    if len(words) > 5:
        words_text += f", ... ({len(words)} всего)"
    words_text += ")"
    
    await callback.message.edit_text(words_text, parse_mode="HTML")
    
    # TODO: Перейти в FSM состояние для редактирования
    # Пока просто информируем пользователя
    await callback.answer("ℹ️ Функция редактирования в разработке", show_alert=False)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def get_user_words(user_id: int) -> list[str]:
    """
    Получить слова из сессии пользователя
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Список слов или пустой список
    """
    session_data = load_user_session(user_id)
    if session_data is None:
        return []
    return session_data.get("words", [])


def clear_user_session(user_id: int):
    """
    Очистить сессию пользователя
    
    Args:
        user_id: ID пользователя
    """
    delete_user_session(user_id)
    logger.debug(f"🗑️ Сессия пользователя {user_id} очищена")
