"""
Обработчик адаптивной сессии обучения в Telegram боте (Этап 6)
Функции: начало сессии, показ слова с адаптивной сложностью, обработка ответа, завершение
"""

import logging
import random
import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.types.input_file import BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from src.bot.states import LearningSessionStates
from src.core.learning_session import LearningSession
from src.core.dictionary_manager import DictionaryManager
from src.core.progress_tracker import ProgressTracker
from src.core.session_persistence import SessionPersistence
from src.services.tts_service import TTSService
from src.services.variant_generator_service import VariantGeneratorService
from src.bot.keyboards.keyboards import get_answer_variants_keyboard, get_end_session_keyboard, get_answer_variants_keyboard_with_pause
from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

router = Router(name="learning_router")

# Инициализация сервисов
dict_manager = DictionaryManager()
tts_service = TTSService()
variant_service = VariantGeneratorService()

# Хранилище активных сессий в памяти
# Ключ: user_id, Значение: LearningSession объект
active_sessions = {}

# Глобальные блокировки для предотвращения гонки условий
session_resume_locks = {}
# ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #3: Добавляем очистку старых Locks
session_lock_cleanup_tasks = {}


async def cleanup_session_lock(session_id: str, delay: int = 3600):
    """
    Очистить Lock сессии через час неиспользования
    
    Args:
        session_id: ID сессии для очистки
        delay: Задержка в секундах перед очисткой (по умолчанию 3600 сек = 1 час)
    """
    try:
        await asyncio.sleep(delay)
        if session_id in session_resume_locks:
            del session_resume_locks[session_id]
            logger.debug(f"🗑️ Lock сессии {session_id} удалён из памяти")
        if session_id in session_lock_cleanup_tasks:
            del session_lock_cleanup_tasks[session_id]
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при очистке Lock сессии {session_id}: {e}")


def generate_simple_variants(word: str) -> list:
    """
    Генерирует простые варианты слова если нет кэша
    Используется как последний fallback механизм
    """
    variants = []
    
    # Вариант 1: Перестановка букв
    if len(word) > 2:
        word_list = list(word)
        for _ in range(3):
            random.shuffle(word_list)
            variants.append(''.join(word_list))
    
    # Вариант 2: Добавление/удаление букв
    if len(word) > 1:
        variants.append(word[:-1] + 'а')
        variants.append(word[:-1] + 'ы')
        variants.append(word[:-1] + 'о')
    
    variants = list(set(variants))
    variants = [v for v in variants if v != word and len(v) > 0]
    
    return variants[:3] if len(variants) >= 3 else variants

# ============================================================================
# НАЧАЛО СЕССИИ ОБУЧЕНИЯ
# ============================================================================

@router.callback_query(F.data.startswith("learning_start:"))
async def callback_start_learning(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Начать обучение" для словаря
    """
    user_id = callback.from_user.id
    dict_id = callback.data.split(":")[1]
    
    logger.info(f"🎓 Пользователь {user_id} начинает обучение со словарём {dict_id}")
    
    try:
        # Получаем словарь
        dictionary = dict_manager.get_dictionary(user_id, dict_id)
        if not dictionary or not dictionary.words:
            await callback.answer("❌ Словарь не найден или пуст", show_alert=True)
            return
        
        # Создаём сессию обучения
        session = LearningSession(
            user_id=user_id,
            dict_id=dict_id,
            dict_name=dictionary.name,
            words_list=dictionary.words
        )
        
        # Сохраняем сессию в памяти
        active_sessions[user_id] = session
        
        # Сохраняем в FSM
        await state.set_state(LearningSessionStates.in_session)
        await state.update_data(session_id=session.session_id, dict_id=dict_id)
        
        # === ПЛАН 0012 Фаза 2.1: Улучшенное стартовое сообщение ===
        # Используем answer() вместо edit_text() для создания нового сообщения
        # Вместо редактирования кнопки "Начать обучение", создаём отдельное сообщение
        text = f"""🎓 **Начинаем обучение!**

📖 Словарь: **{dictionary.name}**
📚 Слов: {len(dictionary.words)}
⏱️ Примерно 18-30 вопросов (зависит от скорости обучения)

Нужно выучить каждое слово до оценки "5"! ✅
Критерий: 3 правильных подряд + 75% успеха

Приготовься... Начинаем через 1 секунду! 🚀"""
        
        # Создаём новое сообщение вместо редактирования
        await callback.message.answer(text, parse_mode="Markdown")
        await callback.answer()
        
        # Задержка перед началом обучения
        await asyncio.sleep(1)
        
        # Показываем первое слово
        await show_next_word(user_id, callback.message.bot, state)
    
    except Exception as e:
        logger.error(f"❌ Ошибка при начале сессии: {e}")
        await callback.answer("❌ Ошибка при начале обучения", show_alert=True)


# ============================================================================
# ПОКАЗ СЛЕДУЮЩЕГО СЛОВА
# ============================================================================

async def show_next_word(user_id: int, bot, state: FSMContext, send_feedback: str = None):
    """
    Показать следующее слово для ответа (с поддержкой адаптивного алгоритма)
    
    Алгоритм:
    1. Выбираем следующее слово по приоритету (адаптивный выбор)
    2. Если все слова выучены - завершаем сессию
    3. Подбираем сложность вариантов на основе количества ошибок
    4. Отправляем аудио и варианты
    
    Args:
        user_id: ID пользователя
        bot: Telegram bot объект
        state: FSMContext
        send_feedback: Опциональный фидбек на предыдущий ответ
    """
    try:
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #6: Проверяем FSM состояние
        current_state = await state.get_state()
        if current_state not in (LearningSessionStates.in_session, LearningSessionStates.waiting_for_answer):
            logger.warning(f"⚠️ Неверное состояние FSM для пользователя {user_id}: {current_state}. Ожидается in_session или waiting_for_answer.")
            return
        
        # Получаем активную сессию
        session = active_sessions.get(user_id)
        if not session:
            logger.error(f"❌ Сессия не найдена для пользователя {user_id}")
            await bot.send_message(user_id, "❌ Ошибка: сессия потеряна")
            return
        
        # === АДАПТИВНЫЙ ВЫБОР СЛЕДУЮЩЕГО СЛОВА ===
        current_word = session.get_next_word()
        
        # Если слов больше нет - завершаем сессию
        if current_word is None:
            await finish_learning_session(user_id, bot, state)
            return
        
        # Добавляю страховку против выученных слов
        word_obj = session.get_word_data(current_word)
        if word_obj and word_obj.is_mastered:
            logger.warning(f"⚠️ Страховка! Слово '{current_word}' отмечено как выученное. Пропускаем и ищем следующее.")
            await show_next_word(user_id, bot, state, send_feedback=send_feedback)
            return
        
        # === ПЛАН 0012 Фаза 2.2: Убрать автоудаление промежуточного прогресса ===
        # Промежуточный прогресс остаётся в чате как milestone (не удаляется)
        if session.should_show_progress_update():
            progress_msg = await bot.send_message(
                user_id,
                session.get_progress_update(),
                parse_mode="Markdown"
            )
            # ✅ УДАЛЕНО: автоудаление через 4 секунды
            # Промежуточный прогресс теперь остаётся в истории чата
        
        # === АДАПТИВНАЯ СЛОЖНОСТЬ ВАРИАНТОВ ===
        # (Новая логика: всегда показываем одни и те же 3 варианта)
        word_obj = session.get_word_data(current_word)
        
        # Получаем все 3 варианта для слова
        wrong_variants = []
        try:
            wrong_variants = variant_service.get_all_variants(current_word)
            
            if wrong_variants and len(wrong_variants) == 3:
                logger.debug(f"✅ Варианты найдены для '{current_word}': {wrong_variants}")
            else:
                logger.warning(f"⚠️ Варианты для '{current_word}' не найдены или неполные. Генерируем новые...")
                try:
                    new_variants = await variant_service.generate_variants_single(current_word)
                    if new_variants and isinstance(new_variants, list) and len(new_variants) == 3:
                        wrong_variants = new_variants
                        logger.info(f"✅ Сгенерированы новые варианты для '{current_word}': {wrong_variants}")
                    else:
                        wrong_variants = generate_simple_variants(current_word)
                except Exception as gen_err:
                    logger.warning(f"⚠️ Не удалось сгенерировать варианты: {gen_err}")
                    wrong_variants = generate_simple_variants(current_word)
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении вариантов: {e}")
            wrong_variants = generate_simple_variants(current_word)
        
        if not wrong_variants:
            logger.error(f"❌ Не удалось получить варианты для слова '{current_word}'")
            await bot.send_message(user_id, "❌ Ошибка при загрузке вариантов ответа.")
            return
        
        # === АУДИО ПРОИЗНОШЕНИЯ ===
        audio_bytes = None
        try:
            audio_bytes = await tts_service.generate_audio(current_word)
            if audio_bytes:
                logger.debug(f"🔊 Аудио получено для слова '{current_word}' ({len(audio_bytes)} байт)")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить аудио: {e}")
        
        # === ОТПРАВЛЯЕМ ГОЛОСОВОЕ СООБЩЕНИЕ ===
        voice_message_id = None
        if audio_bytes:
            try:
                voice_msg = await bot.send_voice(
                    chat_id=user_id,
                    voice=BufferedInputFile(file=audio_bytes, filename=f"{current_word}.mp3")
                )
                voice_message_id = voice_msg.message_id
                logger.info(f"🔊 Голосовое сообщение отправлено для слова '{current_word}'")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить голосовое сообщение: {e}")
        
        # === ОТПРАВЛЯЕМ ВАРИАНТЫ ОТВЕТОВ С КНОПКОЙ ПАУЗЫ (ПРОБЛЕМА #1) ===
        keyboard_data = get_answer_variants_keyboard_with_pause(current_word, wrong_variants, session.session_id)
        if not keyboard_data:
            logger.error(f"❌ Не удалось создать клавиатуру для слова '{current_word}'")
            await bot.send_message(user_id, "❌ Ошибка при создании клавиатуры")
            return
        
        # === ПЛАН 0012 Фаза 2.4: Добавить индикатор прогресса ===
        mastered = session.get_mastered_count()
        total = len(session.words)
        position = session.get_current_position()
        
        progress_text = f"📊 Выучено: {mastered}/{total} | Вопрос #{position}"
        message_text = f"{progress_text}\n\n🔤 Выбери правильное слово:"
        
        msg = await bot.send_message(
            user_id,
            message_text,
            reply_markup=keyboard_data['keyboard']
        )
        
        # Устанавливаем состояние ожидания ответа
        await state.set_state(LearningSessionStates.waiting_for_answer)
        await state.update_data(
            current_word=current_word,
            message_id=msg.message_id,
            voice_message_id=voice_message_id
        )
        
        progress = session.get_word_data(current_word)
        logger.info(f"📝 Слово показано: '{current_word}' (ошибок: {progress.incorrect_count}, попыток: {progress.total_attempts})")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при показе слова: {e}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)}")


# ============================================================================
# ОБРАБОТКА ОТВЕТА
# ============================================================================

@router.callback_query(F.data.startswith("answer:"), LearningSessionStates.waiting_for_answer)
async def callback_handle_answer(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбранного варианта ответа (адаптивный алгоритм)
    ✅ План 0012 Фаза 3.1: Защита от повторных нажатий
    ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #5: Добавлена ранняя проверка наличия сессии
    """
    user_id = callback.from_user.id
    
    try:
        # === ПЛАН 0012 Фаза 3.1: Защита от повторных нажатий ===
        # Сразу отвечаем на callback
        await callback.answer()
        
        # Проверяем FSM состояние
        current_state = await state.get_state()
        if current_state != LearningSessionStates.waiting_for_answer:
            logger.warning(f"⚠️ Дубликат ответа от {user_id}. Игнорируем (состояние={current_state})")
            return
        
        # Сразу меняем состояние на in_session чтобы заблокировать повторные нажатия
        await state.set_state(LearningSessionStates.in_session)
        
        # ПРОБЛЕМА #5: Ранняя проверка наличия сессии
        session = active_sessions.get(user_id)
        if not session:
            logger.error(f"❌ Сессия не найдена для пользователя {user_id} при обработке ответа")
            await state.clear()  # Очищаем FSM
            await callback.answer("❌ Сессия потеряна. Начните заново.", show_alert=True)
            return
        state_data = await state.get_data()
        voice_message_id = state_data.get('voice_message_id')
        
        if voice_message_id:
            try:
                await callback.message.bot.delete_message(chat_id=user_id, message_id=voice_message_id)
                logger.debug(f"🗑️ Голосовое сообщение удалено после ответа")
            except Exception as del_err:
                logger.warning(f"⚠️ Не удалось удалить голосовое сообщение: {del_err}")
        
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            logger.error(f"❌ Некорректный формат callback_data: {callback.data}")
            await callback.answer("❌ Ошибка при обработке ответа")
            return
        
        correct_word = parts[1].strip()
        selected_variant = parts[2].strip()
        
        if not correct_word or not selected_variant:
            logger.error(f"❌ Невалидные данные: correct_word='{correct_word}', selected_variant='{selected_variant}'")
            await callback.answer("❌ Невалидные данные", show_alert=True)
            return
        
        # Session уже проверена в начале функции - используем её напрямую
        current_word = session.get_current_word()
        if correct_word != current_word:
            logger.error(f"❌ Несоответствие слова: callback_word='{correct_word}' != session_word='{current_word}'")
            await callback.answer("❌ Слово изменилось! Перезагрузи сессию.", show_alert=True)
            return
        
        # Проверяем ответ
        is_correct = (selected_variant == correct_word)
        
        # Записываем результат в сессию
        session.record_answer(correct_word, is_correct)
        
        # Получаем объект слова для проверки статуса
        word_obj = session.get_word_data(correct_word)
        
        # Формируем фидбек
        if is_correct:
            feedback = f"✅ **Правильно!**\n**{correct_word}**"
            logger.info(f"✅ Правильный ответ от пользователя {user_id} для слова '{correct_word}'")
        else:
            feedback = f"❌ **Неправильно!**\n**{correct_word}**"
            logger.info(f"❌ Неправильный ответ от пользователя {user_id}: выбрал '{selected_variant}' вместо '{correct_word}'")
        
        # === ДОПОЛНИТЕЛЬНОЕ СООБЩЕНИЕ ЕСЛИ СЛОВО ВЫУЧЕНО НА 5 ===
        mastered_message = ""
        if word_obj and word_obj.is_mastered:
            progress_data = session.get_progress_update()
            mastered_message = f"✨ **СЛОВО ВЫУЧЕНО НА 5!** ✨\n{correct_word}\n\n"
        
        # === ОТПРАВЛЯЕМ ФИДБЕК БЕЗ АВТОУДАЛЕНИЯ ===
        # (уже вызывали callback.answer() выше)
        await callback.message.delete()
        
        combined_feedback = mastered_message + feedback if mastered_message else feedback
        feedback_msg = await callback.message.bot.send_message(
            user_id,
            combined_feedback,
            parse_mode="Markdown"
        )
        
        # === ПЛАН 0012 Фаза 2.3: Убрать автоудаление фидбек сообщений ===
        # Фидбек остаётся в истории чата как подтверждение правильности/неправильности
        
        # Проверяем завершена ли сессия
        if session.is_complete():
            # Сессия завершена - переходим к финализации
            await finish_learning_session(user_id, callback.message.bot, state)
        else:
            # Продолжаем обучение - показываем следующее слово
            # ✅ УДАЛЕНО: автоудаление фидбек сообщения (было sleep(3) и delete)
            asyncio.create_task(show_next_word(user_id, callback.message.bot, state))
    
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке ответа: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# ============================================================================
# ЗАВЕРШЕНИЕ СЕССИИ
# ============================================================================

async def finish_learning_session(user_id: int, bot, state: FSMContext, last_feedback: str = None):
    """
    Завершить адаптивную сессию обучения и показать статистику
    Сохраняет прогресс через ProgressTracker
    
    Args:
        user_id: ID пользователя
        bot: Telegram bot объект
        state: FSMContext
        last_feedback: Опциональный фидбек на последний ответ
    """
    try:
        # Получаем сессию
        session = active_sessions.get(user_id)
        if not session:
            logger.error(f"❌ Сессия не найдена при завершении")
            await bot.send_message(user_id, "❌ Ошибка: сессия потеряна")
            return
        
        # Завершаем сессию и получаем статистику
        stats = session.finish_session()
        
        # === СОХРАНЯЕМ ПРОГРЕСС ЧЕРЕЗ PROGRESS TRACKER ===
        try:
            progress_tracker = ProgressTracker(user_id)
            
            # Обновляем статистику сессии
            progress_tracker.update_session_stats(
                dict_id=session.dict_id,
                correct_count=stats.correct_answers,
                incorrect_count=stats.incorrect_answers,
                words_mastered=stats.words_mastered_list
            )
            
            # === СОХРАНЯЕМ SESSIONSTATS В ФАЙЛЫ ===
            try:
                from pathlib import Path
                from src.utils.file_helpers import save_json
                user_data_dir = DATA_DIR / "users" / str(user_id)
                sessions_dir = user_data_dir / "sessions"
                sessions_dir.mkdir(parents=True, exist_ok=True)
                
                stats_file = sessions_dir / f"{session.session_id}.json"
                stats_dict = stats.model_dump(mode='json')
                save_json(str(stats_file), stats_dict)
                
                logger.info(f"✅ SessionStats сохранены: {stats_file}")
            except Exception as save_err:
                logger.error(f"⚠️ Ошибка при сохранении SessionStats: {save_err}")
            
            logger.info(f"✅ Прогресс сохранён для пользователя {user_id}")
        except Exception as progress_err:
            logger.error(f"⚠️ Ошибка при сохранении прогресса: {progress_err}")
        
        # === ОБНОВЛЯЕМ СТАТУС СЛОВАРЯ ===
        if stats.is_complete:
            try:
                dictionary = dict_manager.get_dictionary(user_id, session.dict_id)
                if dictionary:
                    dictionary.is_fully_learned = True
                    dictionary.last_session_date = datetime.now()
                    dictionary.total_sessions += 1
                    dict_manager.update_dictionary(
                        user_id,
                        session.dict_id,
                        dictionary.words
                    )
                    logger.info(f"✅ Словарь '{session.dict_name}' отмечен как полностью выученный")
            except Exception as dict_err:
                logger.error(f"⚠️ Ошибка при обновлении словаря: {dict_err}")
        
        # Формируем итоговое сообщение
        summary = session.get_summary()
        
        # Если есть последний фидбек - добавляем его
        if last_feedback:
            summary = f"{last_feedback}\n\n{summary}"
        
        # Создаём клавиатуру для конца сессии
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="📚 Мои словари", callback_data="view_dictionaries")
        keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
        keyboard.adjust(2)
        
        # Отправляем итоговое сообщение
        await bot.send_message(
            user_id,
            summary,
            parse_mode="Markdown",
            reply_markup=keyboard.as_markup()
        )
        
        # Удаляем сессию из памяти
        del active_sessions[user_id]
        
        # Очищаем FSM
        await state.clear()
        
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #7: Удаляем сохранённую сессию с диска после завершения
        await SessionPersistence.delete_session(user_id, session.session_id)
        
        logger.info(f"✅ Сессия завершена для пользователя {user_id}. Статистика: {stats}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при завершении сессии: {e}")
        await bot.send_message(user_id, f"❌ Ошибка при завершении сессии: {str(e)}")


# ============================================================================
# ОБРАБОТЧИК ПАУЗЫ СЕССИИ (Этап 8)
# ============================================================================

@router.callback_query(F.data.startswith("pause_session:"))
async def callback_pause_session(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Пауза" для сохранения и приостановки сессии (Этап 8)
    """
    user_id = callback.from_user.id
    session_id = callback.data.split(":")[1]
    
    logger.info(f"⏸️ Пользователь {user_id} поставил сессию на паузу: {session_id}")
    
    try:
        session = active_sessions.get(user_id)
        if not session:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            return
        
        if session.session_id != session_id:
            await callback.answer("❌ ID сессии не совпадает", show_alert=True)
            return
        
        # Сохраняем состояние сессии в FSM
        await state.update_data(
            paused_session_id=session_id,
            paused_session_data={
                'user_id': user_id,
                'dict_id': session.dict_id,
                'dict_name': session.dict_name,
                'current_word': session.current_word,
                'total_correct': session.stats.correct_answers,
                'total_incorrect': session.stats.incorrect_answers
            }
        )
        
        # Удаляем сессию из памяти
        del active_sessions[user_id]
        
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #7: Сохраняем сессию на диск перед паузой
        await SessionPersistence.save_session(user_id, session)
        
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #4: НЕ очищаем состояние! Устанавливаем состояние паузы
        await state.set_state(LearningSessionStates.session_paused)
        
        # Отправляем сообщение о паузе
        pause_text = f"""⏸️ **СЕССИЯ СОХРАНЕНА**

📖 Словарь: **{session.dict_name}**
⏱️ Сессия ID: `{session_id}`

Прогресс сохранён! Ты можешь вернуться когда будешь готов.

**Текущая статистика:**
✅ Правильно: {session.stats.correct_answers}
❌ Неправильно: {session.stats.incorrect_answers}"""
        
        from src.bot.keyboards.keyboards import get_session_paused_keyboard
        await callback.message.edit_text(
            pause_text,
            parse_mode="Markdown",
            reply_markup=get_session_paused_keyboard(session_id)
        )
        
        await callback.answer()
        logger.info(f"✅ Сессия {session_id} сохранена для пользователя {user_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при паузе сессии: {e}")
        await callback.answer(f"❌ Ошибка при паузе: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("resume_session:"))
async def callback_resume_session(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Продолжить обучение" для восстановления сессии (Этап 8)
    ИСПРАВЛЕНИЕ ПРОБЛЕМА #3: Защита от race conditions через asyncio.Lock
    """
    user_id = callback.from_user.id
    session_id = callback.data.split(":")[1]
    
    logger.info(f"▶️ Пользователь {user_id} возобновляет сессию: {session_id}")
    
    try:
        # ПРОБЛЕМА #3: Создаём/получаем лок для этой сессии
        if session_id not in session_resume_locks:
            session_resume_locks[session_id] = asyncio.Lock()
        
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #3: Добавляем тайм-аут для защиты от deadlock
        try:
            async with asyncio.timeout(30):  # 30 секунд тайм-аут
                async with session_resume_locks[session_id]:
                    # Проверяем, что сессия не была уже возобновлена
                    if user_id in active_sessions:
                        await callback.answer("⚠️ Сессия уже в процессе", show_alert=True)
                        return
                    
                    # Получаем сохранённые данные сессии
                    state_data = await state.get_data()
                    paused_data = state_data.get('paused_session_data')
                    
                    if not paused_data:
                        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА! Сохранённые данные сессии потеряны! state_data={state_data}")
                        await callback.answer("❌ Сохранённые данные сессии не найдены. Начните обучение заново.", show_alert=True)
                        await state.clear()
                        return
                    
                    # Восстанавливаем сессию через SessionPersistence (полное состояние)
                    session = await SessionPersistence.load_session(user_id, session_id)  # ✅ Передаём оба параметра
                    if not session:
                        await callback.answer("❌ Сохранённые данные сессии не найдены. Начните обучение заново.", show_alert=True)
                        await state.clear()
                        return
                    
                    # ✅ Сессия полностью восстановлена со всеми данными:
                    # - Все слова со статусами
                    # - Полный прогресс каждого слова
                    # - Статистика сессии (correct_answers, incorrect_answers, etc.)
                    
                    # Сохраняем восстановленную сессию в памяти
                    active_sessions[user_id] = session
                    
                    # Устанавливаем FSM состояние
                    await state.set_state(LearningSessionStates.in_session)
                    await state.update_data(session_id=session.session_id, dict_id=paused_data['dict_id'])
                    
                    # Отправляем сообщение о возобновлении
                    resume_text = f"""▶️ **ОБУЧЕНИЕ ВОЗОБНОВЛЕНО!**

📖 Словарь: **{paused_data['dict_name']}**

Продолжаем отсюда... 🚀"""
                    
                    await callback.message.edit_text(resume_text, parse_mode="Markdown")
                    await callback.answer()
                    
                    # Показываем следующее слово
                    await show_next_word(user_id, callback.message.bot, state)
                    logger.info(f"✅ Сессия {session_id} возобновлена для пользователя {user_id}")
                    
                    # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #3: Запускаем cleanup задачу для этого Lock
                    if session_id not in session_lock_cleanup_tasks:
                        cleanup_task = asyncio.create_task(cleanup_session_lock(session_id))
                        session_lock_cleanup_tasks[session_id] = cleanup_task
        except asyncio.TimeoutError:
            logger.error(f"❌ Ошибка таймаута при возобновлении сессии {session_id} для пользователя {user_id}")
            await callback.answer("❌ Ошибка: таймаут при возобновлении сессии. Попробуйте позже.", show_alert=True)
        except Exception as e:
            logger.error(f"❌ Ошибка при возобновлении сессии: {e}")
            await callback.answer(f"❌ Ошибка при возобновлении: {str(e)}", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Ошибка при восстановлении сессии: {e}")
        await callback.answer(f"❌ Критическая ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("end_paused_session:"))
async def callback_end_paused_session(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик для завершения паузированной сессии (Этап 8)
    """
    user_id = callback.from_user.id
    session_id = callback.data.split(":")[1]
    
    logger.info(f"⏹️ Пользователь {user_id} завершает паузированную сессию: {session_id}")
    
    try:
        end_text = """✅ **Сессия завершена**

Твой прогресс был сохранён! 💾

Когда будешь готов продолжить, можешь выбрать другой словарь или начать обучение заново."""
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="📚 Мои словари", callback_data="view_dictionaries")
        keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
        keyboard.adjust(2)
        
        await callback.message.edit_text(
            end_text,
            parse_mode="Markdown",
            reply_markup=keyboard.as_markup()
        )
        
        await callback.answer()
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #4: Очищаем FSM ДО КОНЦА, после завершения паузированной сессии
        # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМА #7: Удаляем сохранённую сессию с диска ПЕРЕД очисткой
        state_data = await state.get_data()
        paused_session_id = state_data.get('paused_session_id', None) if state_data else None
        
        await state.clear()
        
        if paused_session_id:
            await SessionPersistence.delete_session(user_id, paused_session_id)
        logger.info(f"✅ Паузированная сессия {session_id} завершена для пользователя {user_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при завершении паузированной сессии: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# ============================================================================
# ОБРАБОТЧИК ДЛЯ ПОВТОРА ОБУЧЕНИЯ
# ============================================================================

@router.callback_query(F.data == "repeat_learning")
async def callback_repeat_learning(callback: CallbackQuery):
    """
    Обработчик кнопки "Начать заново"
    """
    user_id = callback.from_user.id
    
    logger.info(f"🔄 Пользователь {user_id} хочет повторить обучение")
    
    # Возвращаем в меню со словарями
    from src.bot.handlers.dictionary_handler import show_dictionaries
    await show_dictionaries(user_id, callback, is_callback=True)
