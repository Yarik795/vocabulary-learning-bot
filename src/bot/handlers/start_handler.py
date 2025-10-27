"""
Обработчик команды /start и главное меню
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, BaseFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from src.bot.states import DictionaryStates, LearningSessionStates

logger = logging.getLogger(__name__)

# Создание роутера для обработчиков
router = Router()


# ============================================================================
# КАСТОМНЫЕ ФИЛЬТРЫ
# ============================================================================

class NotInEditingMode(BaseFilter):
    """
    Фильтр: True если пользователь НЕ в режиме редактирования словаря
    
    Используется для handle_unknown, чтобы он не обрабатывал сообщения
    при активном FSM состоянии waiting_for_words
    """
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        is_not_editing = current_state != DictionaryStates.waiting_for_words
        if not is_not_editing:
            logger.debug(f"🔍 NotInEditingMode фильтр ОТКЛОНИЛ: состояние = waiting_for_words")
        return is_not_editing


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """
    Обработчик команды /start
    Приветствие пользователя и показ главного меню
    
    ✅ План 0012 Фаза 1: Защита от прерывания сессии командами
    - Проверяет активна ли сессия обучения
    - Если да, показывает предупреждение вместо главного меню
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Ученик"
    
    # === ПЛАН 0012 Фаза 1: Проверка активной сессии ===
    current_state = await state.get_state()
    if current_state in (LearningSessionStates.in_session, LearningSessionStates.waiting_for_answer):
        # Получаем данные сессии из состояния
        state_data = await state.get_data()
        session_id = state_data.get('session_id', '?')
        
        logger.info(f"⚠️ Пользователь {user_id} попытался открыть /start во время активной сессии {session_id}")
        
        # Импортируем здесь чтобы избежать циклической зависимости
        from src.bot.handlers.learning_handler import active_sessions
        
        session = active_sessions.get(user_id)
        if session:
            warning_text = f"""⚠️ **У тебя активна сессия обучения!**

📖 **Словарь:** {session.dict_name}
📊 **Прогресс:** {session.get_mastered_count()}/{len(session.words)} выучено

Что сделать?"""
            
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="⏸️ Поставить на паузу и перейти в меню", callback_data="pause_and_menu")
            keyboard.button(text="❌ Отмена (продолжить обучение)", callback_data="cancel_menu_switch")
            keyboard.adjust(1)
            
            await message.answer(warning_text, reply_markup=keyboard.as_markup())
            return
    
    logger.info(f"✅ Пользователь: {user_id} ({user_name})")
    
    welcome_text = f"""👋 Привет, {user_name}!

Добро пожаловать в бот для изучения словарных слов! 📚

Я помогу тебе выучить правописание словарных слов через:
✨ Распознавание текста с фотографий
🔊 Озвучивание каждого слова
❓ Интерактивные тесты с выбором правильного варианта
📊 Отслеживание прогресса

Как это работает:
1️⃣ Отправь фотографию со списком слов
2️⃣ Я распознаю текст
3️⃣ Мы будем учить слова до полного усвоения (оценка "5")
4️⃣ Видишь свой прогресс в реальном времени

Давай начнём! Нажми кнопку ниже. 👇"""

    # Создаём inline клавиатуру для главного меню
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📚 Создать словарь (загрузить фото)", callback_data="upload_photo")
    keyboard.button(text="📖 Мои словари", callback_data="view_dictionaries")
    keyboard.button(text="📊 Мой прогресс", callback_data="show_progress")
    keyboard.button(text="❓ Справка", callback_data="help")
    keyboard.adjust(1)
    
    await message.answer(
        welcome_text,
        reply_markup=keyboard.as_markup()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Обработчик команды /help
    Показ справки о возможностях бота (Этап 8)
    """
    help_text = """📖 **СПРАВКА ПО БОТУ**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**⚡ ОСНОВНЫЕ КОМАНДЫ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/start - главное меню
/help - эта справка
/menu - возврат в меню

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📸 СОЗДАНИЕ СЛОВАРЯ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Фотографируешь список слов
2️⃣ Отправляешь фото боту
3️⃣ Я распознаю текст и предлагаю отредактировать
4️⃣ После подтверждения - автоматическая подготовка к обучению
5️⃣ Варианты ответов генерируются за несколько секунд

**Требования к фото:**
✅ Чёткий текст на светлом фоне
✅ Естественное освещение
✅ Размер: 100×100 пикселей минимум
✅ Файл: до 10MB

**Ограничения:**
📝 Максимум **50 слов** в словаре
💡 Совет: создавай несколько словарей!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**🎓 ОБУЧЕНИЕ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 🔊 Озвучивание каждого слова
• ❓ Выбор из 4 вариантов
• 📊 Адаптивная сложность
• 🎯 Оценка "5" = 3 подряд + 75% успеха

**НОВОЕ в Этап 8 - ПАУЗА СЕССИИ:**
⏸️ Нажми "⏸️ Пауза" во время обучения
💾 Прогресс сохранится автоматически
▶️ Продолжи обучение позже кнопкой "▶️ Продолжить"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📚 УПРАВЛЕНИЕ СЛОВАРЯМИ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 Просмотр всех словарей
✏️ Редактирование (макс 50 слов)
🗑️ Удаление с подтверждением
📈 История обучения

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📊 СТАТИСТИКА:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 Общая статистика
📊 % успешных ответов
🎯 Выученные слова
📜 История последних 10 сессий

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**💡 СОВЕТЫ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ Учи меньше слов, но тщательнее
✨ Используй встроенную камеру
✨ При ошибке читай подсказку
✨ Создавай тематические словари

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**🆘 ЕСЛИ НЕ РАБОТАЕТ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Прочитай ошибку (там совет!)
2️⃣ Подожди 30 сек и повтори
3️⃣ Проверь интернет
4️⃣ Нажми /start

**Удачи! 💪 Ты сможешь! 🚀**"""

    await message.answer(help_text, parse_mode="Markdown")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    """
    Показ главного меню
    
    ✅ План 0012 Фаза 1: Защита от прерывания сессии командами
    """
    await cmd_start(message, state)


@router.message(F.text, ~F.text.startswith("/"), NotInEditingMode())
async def handle_unknown(message: Message, state: FSMContext):
    """
    Обработчик неизвестных команд (только текстовые сообщения)
    
    Проверяет: может это редактирование словаря?
    Если да - пропускает обработку, пусть dictionary_handler справится
    Если нет - обрабатывает как неизвестную команду
    """
    user_id = message.from_user.id
    current_state = await state.get_state()
    
    # 🔍 ОТЛАДКА: Логируем ВСЕ входящие текстовые сообщения
    logger.info(f"📨 handle_unknown ПОЛУЧИЛ сообщение от {user_id}: '{message.text[:50]}...' | FSM состояние: {current_state}")
    
    # 🔍 КРИТИЧНО: Проверить, находимся ли мы в режиме редактирования словаря
    if current_state == DictionaryStates.waiting_for_words:
        # Это сообщение должно обработать handle_edited_dictionary в dictionary_handler
        logger.info(f"⏭️  Пропускаем handle_unknown для {user_id} → handle_edited_dictionary обработает (FSM: waiting_for_words)")
        return
    
    logger.warning(f"❌ handle_unknown сработал! Пользователь {user_id}")
    logger.warning(f"   - message.text: {message.text}")
    logger.warning(f"   - message.photo: {message.photo if hasattr(message, 'photo') else 'N/A'}")
    logger.warning(f"   - message.content_type: {message.content_type if hasattr(message, 'content_type') else 'N/A'}")
    logger.warning(f"Неизвестная команда от {user_id}: {message.text}")
    
    await message.answer(
        "❓ Я не понимаю эту команду.\n\n"
        "Используй /start для главного меню или /help для справки."
    )


# ============================================================================
# ОБРАБОТЧИКИ ЗАЩИТЫ ОТ ПРЕРЫВАНИЯ СЕССИИ (План 0012 Фаза 1)
# ============================================================================

@router.callback_query(F.data == "pause_and_menu")
async def callback_pause_and_menu(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Поставить на паузу и перейти в меню"
    
    ✅ План 0012 Фаза 1: Защита от прерывания сессии командами
    """
    user_id = callback.from_user.id
    
    logger.info(f"⏸️ Пользователь {user_id} нажал кнопку 'Поставить на паузу'")
    
    # Получаем текущую сессию
    from src.bot.handlers.learning_handler import active_sessions, SessionPersistence
    
    session = active_sessions.get(user_id)
    if session:
        # Сохраняем сессию на диск
        session_persistence = SessionPersistence()
        session_persistence.save_session(user_id, session)
        del active_sessions[user_id]
        
        logger.info(f"✅ Сессия {session.session_id} сохранена для пользователя {user_id}")
    
    # Очищаем состояние FSM
    await state.clear()
    
    # Показываем главное меню
    welcome_text = f"""👋 Привет!

Добро пожаловать в бот для изучения словарных слов! 📚

Сессия сохранена! ✅
Ты можешь продолжить обучение позже через "Мои словари" → "Продолжить обучение"

Что дальше?"""
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📚 Создать словарь (загрузить фото)", callback_data="upload_photo")
    keyboard.button(text="📖 Мои словари", callback_data="view_dictionaries")
    keyboard.button(text="📊 Мой прогресс", callback_data="show_progress")
    keyboard.button(text="❓ Справка", callback_data="help")
    keyboard.adjust(1)
    
    await callback.message.edit_text(welcome_text, reply_markup=keyboard.as_markup())
    await callback.answer()


@router.callback_query(F.data == "cancel_menu_switch")
async def callback_cancel_menu_switch(callback: CallbackQuery):
    """
    Обработчик кнопки "Отмена (продолжить обучение)"
    
    ✅ План 0012 Фаза 1: Защита от прерывания сессии командами
    """
    user_id = callback.from_user.id
    
    logger.info(f"❌ Пользователь {user_id} отменил переход в меню")
    
    await callback.answer("✅ Продолжаем обучение!", show_alert=False)


# ============================================================================
# ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ
# ============================================================================

@router.callback_query(F.data == "upload_photo")
async def callback_upload_photo(callback: CallbackQuery):
    """
    Обработчик кнопки 'Создать словарь' - показываем инструкцию
    """
    user_id = callback.from_user.id
    logger.info(f"📸 Пользователь {user_id} нажал кнопку загрузки фото")
    
    instruction_text = """📸 **Загрузи фотографию со списком слов**

Требования к фотографии:
✅ Чёткий текст на белом фоне
✅ Хорошее освещение
✅ Размер: минимум 100x100 пикселей
✅ Максимум 50 слов
❌ Не размытые фото
❌ Не фото с картинками

Когда загружу фото, я:
1. Распознам все слова
2. Очищу от ошибок распознавания
3. Покажу список для редактирования
4. Подготовлю варианты для обучения

Отправь фото сейчас! 👇"""

    await callback.message.edit_text(instruction_text, parse_mode="Markdown")
    await callback.answer()
    logger.info(f"✅ Инструкция отправлена пользователю {user_id}")


@router.callback_query(F.data == "view_dictionaries")
async def callback_view_dictionaries(callback: CallbackQuery):
    """
    Обработчик кнопки 'Мои словари'
    """
    user_id = callback.from_user.id
    logger.info(f"📚 Пользователь {user_id} нажал кнопку 'Мои словари'")
    
    # Импортируем функцию из dictionary_handler
    from src.bot.handlers.dictionary_handler import show_dictionaries
    await show_dictionaries(user_id, callback, is_callback=True)
    await callback.answer()


@router.callback_query(F.data == "show_progress")
async def callback_view_progress(callback: CallbackQuery):
    """
    Обработчик кнопки 'Мой прогресс'
    """
    user_id = callback.from_user.id
    logger.info(f"📊 Пользователь {user_id} нажал кнопку 'Мой прогресс'")
    
    # Импортируем функцию из progress_handler
    from src.bot.handlers.progress_handler import show_progress_statistics
    await show_progress_statistics(user_id, callback=callback)


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """
    Обработчик кнопки 'Справка' (Этап 8)
    """
    user_id = callback.from_user.id
    logger.info(f"❓ Пользователь {user_id} нажал кнопку 'Справка'")
    
    help_text = """📖 **СПРАВКА ПО БОТУ**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**⚡ ОСНОВНЫЕ КОМАНДЫ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/start - главное меню
/help - эта справка
/menu - возврат в меню

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📸 СОЗДАНИЕ СЛОВАРЯ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Фотографируешь список слов
2️⃣ Отправляешь фото боту
3️⃣ Я распознаю текст и предлагаю отредактировать
4️⃣ После подтверждения - автоматическая подготовка
5️⃣ Варианты ответов генерируются за несколько секунд

**Требования к фото:**
✅ Чёткий текст на светлом фоне
✅ Естественное освещение
✅ Размер: 100×100 пикселей минимум
✅ Файл: до 10MB

**Ограничения:**
📝 Максимум **50 слов** в словаре
💡 Совет: создавай несколько словарей!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**🎓 ОБУЧЕНИЕ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 🔊 Озвучивание каждого слова
• ❓ Выбор из 4 вариантов
• 📊 Адаптивная сложность
• 🎯 Оценка "5" = 3 подряд + 75% успеха

**НОВОЕ в Этап 8 - ПАУЗА СЕССИИ:**
⏸️ Нажми "⏸️ Пауза" во время обучения
💾 Прогресс сохранится автоматически
▶️ Продолжи обучение позже кнопкой "▶️ Продолжить"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📚 УПРАВЛЕНИЕ СЛОВАРЯМИ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 Просмотр всех словарей
✏️ Редактирование (макс 50 слов)
🗑️ Удаление с подтверждением
📈 История обучения

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📊 СТАТИСТИКА:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 Общая статистика
📊 % успешных ответов
🎯 Выученные слова
📜 История последних 10 сессий

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**💡 СОВЕТЫ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ Учи меньше слов, но тщательнее
✨ Используй встроенную камеру
✨ При ошибке читай подсказку
✨ Создавай тематические словари

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**🆘 ЕСЛИ НЕ РАБОТАЕТ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Прочитай ошибку (там совет!)
2️⃣ Подожди 30 сек и повтори
3️⃣ Проверь интернет
4️⃣ Нажми /start

**Удачи! 💪 Ты сможешь! 🚀**"""
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
    keyboard.adjust(1)
    
    await callback.message.edit_text(
        help_text, 
        parse_mode="Markdown",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()

