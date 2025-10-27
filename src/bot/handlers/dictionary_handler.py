"""
Обработчики для управления словарями в Telegram боте
Функции: просмотр, редактирование, удаление словарей
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from src.core.dictionary_manager import DictionaryManager
from aiogram.fsm.context import FSMContext
from src.bot.states import DictionaryStates
from src.utils.validators import clean_words_list

logger = logging.getLogger(__name__)

# Создание роутера для обработчиков словарей
router = Router()

# Инициализация менеджера словарей
dict_manager = DictionaryManager()


# ============================================================================
# ПРОСМОТР СПИСКА СЛОВАРЕЙ
# ============================================================================

async def show_dictionaries(user_id: int, message_or_callback, is_callback: bool = False):
    """
    Показать список всех словарей пользователя
    
    Args:
        user_id: ID пользователя
        message_or_callback: Message или CallbackQuery объект
        is_callback: True если CallbackQuery, False если Message
    """
    try:
        # Получаем список словарей
        dictionaries = dict_manager.list_dictionaries(user_id)
        
        if not dictionaries:
            text = """📚 **Мои словари**

У тебя пока нет словарей.

Создай первый словарь:
1️⃣ Отправь фотографию со списком слов
2️⃣ Я распознам текст
3️⃣ Подтверди список слов
4️⃣ Словарь готов к обучению!

Нажми кнопку "📚 Создать словарь" в главном меню."""
            
            if is_callback:
                await message_or_callback.message.edit_text(text, parse_mode="Markdown")
            else:
                await message_or_callback.answer(text, parse_mode="Markdown")
            return
        
        # Формируем сообщение со списком словарей
        text = f"📚 **Мои словари** ({len(dictionaries)} шт.)\n\n"
        
        for i, dictionary in enumerate(dictionaries, 1):
            word_count = len(dictionary.words)
            status = "✅ Выучено" if dictionary.is_fully_learned else f"📖 {word_count} слов"
            created_date = dictionary.created_at.strftime("%d.%m.%y")
            
            text += f"{i}. **{dictionary.name}**\n"
            text += f"   {status} | Создан: {created_date}\n\n"
        
        # Создаём inline клавиатуру для выбора словаря
        keyboard = InlineKeyboardBuilder()
        for dictionary in dictionaries:
            button_text = f"📖 {dictionary.name} ({len(dictionary.words)} слов)"
            button_data = f"dict_select:{dictionary.id}"
            keyboard.button(text=button_text, callback_data=button_data)
        
        keyboard.button(text="➕ Создать новый", callback_data="upload_photo")
        keyboard.button(text="◀️ В меню", callback_data="back_to_menu")
        keyboard.adjust(1)
        
        if is_callback:
            await message_or_callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
        else:
            await message_or_callback.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
        
        logger.info(f"✅ Список словарей показан пользователю {user_id}: {len(dictionaries)} словарей")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при показе списка словарей: {e}")
        error_text = "❌ Ошибка при загрузке списка словарей. Попробуй позже."
        if is_callback:
            await message_or_callback.answer(error_text, show_alert=True)
        else:
            await message_or_callback.answer(error_text)


# ============================================================================
# ВЫБОР И ПРОСМОТР СЛОВАРЯ
# ============================================================================

@router.callback_query(F.data.startswith("dict_select:"))
async def callback_select_dictionary(callback: CallbackQuery):
    """
    Обработчик выбора словаря из списка
    """
    user_id = callback.from_user.id
    dict_id = callback.data.split(":")[1]
    
    logger.info(f"📖 Пользователь {user_id} выбрал словарь {dict_id}")
    
    try:
        # Получаем словарь
        dictionary = dict_manager.get_dictionary(user_id, dict_id)
        if not dictionary:
            await callback.answer("❌ Словарь не найден", show_alert=True)
            return
        
        # Формируем сообщение с информацией о словаре
        word_count = len(dictionary.words)
        created_date = dictionary.created_at.strftime("%d.%m.%y %H:%M")
        status = "✅ Выучено" if dictionary.is_fully_learned else f"📖 В процессе обучения"
        
        text = f"""📖 **{dictionary.name}**

📊 **Информация:**
• Слов в словаре: {word_count}
• Статус: {status}
• Сессий обучения: {dictionary.total_sessions}
• Создан: {created_date}

🔤 **Слова:**
"""
        
        # Добавляем список слов (максимум 20 в сообщении)
        words_text = ""
        for i, word in enumerate(dictionary.words[:20], 1):
            words_text += f"{i}. {word}\n"
        
        if len(dictionary.words) > 20:
            words_text += f"... и ещё {len(dictionary.words) - 20} слов"
        
        text += words_text
        
        # Создаём клавиатуру с действиями
        keyboard = InlineKeyboardBuilder()
        
        if not dictionary.is_fully_learned:
            keyboard.button(text="🎓 Начать обучение", callback_data=f"learning_start:{dict_id}")
        
        keyboard.button(text="✏️ Редактировать", callback_data=f"dict_edit:{dict_id}")
        keyboard.button(text="🗑️ Удалить", callback_data=f"dict_delete_confirm:{dict_id}")
        keyboard.button(text="◀️ К списку", callback_data="view_dictionaries")
        keyboard.adjust(1)
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
        await callback.answer()
    
    except Exception as e:
        logger.error(f"❌ Ошибка при выборе словаря: {e}")
        await callback.answer("❌ Ошибка при загрузке словаря", show_alert=True)


# ============================================================================
# РЕДАКТИРОВАНИЕ СЛОВАРЯ
# ============================================================================

@router.callback_query(F.data.startswith("dict_edit:"))
async def callback_edit_dictionary(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки редактирования словаря
    """
    user_id = callback.from_user.id
    dict_id = callback.data.split(":")[1]
    
    logger.info(f"✏️ Пользователь {user_id} редактирует словарь {dict_id}")
    
    try:
        dictionary = dict_manager.get_dictionary(user_id, dict_id)
        if not dictionary:
            await callback.answer("❌ Словарь не найден", show_alert=True)
            return
        
        text = f"""✏️ **Редактирование словаря: {dictionary.name}**

Текущие слова ({len(dictionary.words)} шт):
```
{chr(10).join(dictionary.words)}
```

**Как редактировать:**
1️⃣ Скопируй текст выше
2️⃣ Отредактируй список слов (одно слово на строку)
3️⃣ Отправь мне отредактированный список
4️⃣ Я обновлю словарь

⚠️ **Важно:**
• Максимум 50 слов
• Одно слово на строку
• Только русские буквы и дефисы

Жду твой отредактированный список!"""
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="◀️ Отмена", callback_data=f"dict_select:{dict_id}")
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
        
        # Устанавливаем состояние FSM для отслеживания редактирования
        await state.set_state(DictionaryStates.waiting_for_words)
        await state.update_data(dict_id=dict_id, dict_name=dictionary.name)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при редактировании словаря: {e}")
        await callback.answer("❌ Ошибка при загрузке словаря", show_alert=True)


@router.message(F.text, ~F.text.startswith("/"))
async def handle_edited_dictionary(message: Message, state: FSMContext):
    """
    Обработчик редактированного списка слов
    """
    user_id = message.from_user.id
    current_state = await state.get_state()
    
    # 🔍 ОТЛАДКА: Логируем получение сообщения
    logger.info(f"📨 handle_edited_dictionary ПОЛУЧИЛ сообщение от {user_id} | FSM состояние: {current_state}")
    
    # Проверяем, находимся ли мы в режиме редактирования
    if current_state != DictionaryStates.waiting_for_words:
        logger.debug(f"⏭️  Состояние не совпадает (ожидается: waiting_for_words, получено: {current_state}). Пропускаем.")
        return  # Это не редактирование словаря, обработает другой handler
    
    logger.info(f"✅ Состояние совпадает! Обработка редактирования словаря...")
    
    try:
        # Получаем данные из FSM
        data = await state.get_data()
        dict_id = data.get("dict_id")
        dict_name = data.get("dict_name")
        
        logger.info(f"📦 FSM данные: dict_id={dict_id}, dict_name={dict_name}")
        
        # Проверяем полноту данных FSM
        if not dict_id or not dict_name:
            logger.error(f"❌ FSM data неполная: dict_id={dict_id}, dict_name={dict_name}")
            await message.answer("❌ Ошибка: потеряны данные о словаре. Попробуй снова.")
            await state.clear()
            return
        
        # Парсим слова из сообщения
        words_text = message.text.strip()
        words = [w.strip() for w in words_text.split('\n') if w.strip()]
        
        # Валидация
        if len(words) == 0:
            await message.answer("❌ Список пустой. Отправь минимум 1 слово.")
            return
        
        if len(words) > 50:
            await message.answer(f"❌ Слишком много слов ({len(words)}). Максимум 50.")
            return
        
        # Обновляем словарь
        cleaned_words = clean_words_list(words)
        
        if dict_manager.update_dictionary(user_id, dict_id, cleaned_words):
            text = f"""✅ **Словарь обновлён!**

📖 **{dict_name}**
• Слов: {len(cleaned_words)}

Что дальше?"""
            
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="📖 К словарю", callback_data=f"dict_select:{dict_id}")
            keyboard.button(text="🎓 Начать обучение", callback_data=f"learning_start:{dict_id}")
            keyboard.button(text="📚 Мои словари", callback_data="view_dictionaries")
            keyboard.adjust(1)
            
            await message.answer(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
            logger.info(f"✅ Словарь {dict_id} обновлён: {len(cleaned_words)} слов")
        else:
            await message.answer("❌ Ошибка при обновлении словаря. Попробуй позже.")
        
        # Очищаем состояние FSM
        await state.clear()
    
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке редактирования словаря: {e}")
        await message.answer("❌ Ошибка при обновлении словаря. Попробуй позже.")


# ============================================================================
# УДАЛЕНИЕ СЛОВАРЯ
# ============================================================================

@router.callback_query(F.data.startswith("dict_delete_confirm:"))
async def callback_delete_confirm(callback: CallbackQuery):
    """
    Подтверждение удаления словаря
    """
    user_id = callback.from_user.id
    dict_id = callback.data.split(":")[1]
    
    logger.info(f"🗑️ Пользователь {user_id} подтверждает удаление словаря {dict_id}")
    
    try:
        dictionary = dict_manager.get_dictionary(user_id, dict_id)
        if not dictionary:
            await callback.answer("❌ Словарь не найден", show_alert=True)
            return
        
        text = f"""⚠️ **Подтверждение удаления**

Ты хочешь удалить словарь:
**{dictionary.name}** ({len(dictionary.words)} слов)

❌ Это действие не может быть отменено!

Ты уверен?"""
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Да, удалить", callback_data=f"dict_delete_execute:{dict_id}")
        keyboard.button(text="❌ Отмена", callback_data=f"dict_select:{dict_id}")
        keyboard.adjust(2)
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
        await callback.answer()
    
    except Exception as e:
        logger.error(f"❌ Ошибка при подтверждении удаления: {e}")
        await callback.answer("❌ Ошибка при загрузке словаря", show_alert=True)


@router.callback_query(F.data.startswith("dict_delete_execute:"))
async def callback_delete_execute(callback: CallbackQuery):
    """
    Выполнение удаления словаря
    """
    user_id = callback.from_user.id
    dict_id = callback.data.split(":")[1]
    
    logger.info(f"🗑️ Словарь {dict_id} удаляется (пользователь {user_id})")
    
    try:
        dictionary = dict_manager.get_dictionary(user_id, dict_id)
        dict_name = dictionary.name if dictionary else "Словарь"
        
        if dict_manager.delete_dictionary(user_id, dict_id):
            text = f"""✅ **Словарь удалён**

Словарь "{dict_name}" успешно удалён.

Что дальше?"""
            
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="📚 Мои словари", callback_data="view_dictionaries")
            keyboard.button(text="➕ Создать новый", callback_data="upload_photo")
            keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
            keyboard.adjust(1)
            
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard.as_markup())
            await callback.answer("✅ Словарь удалён", show_alert=True)
        else:
            await callback.answer("❌ Ошибка при удалении словаря", show_alert=True)
    
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении словаря: {e}")
        await callback.answer("❌ Ошибка при удалении словаря", show_alert=True)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ОБРАБОТЧИКИ
# ============================================================================

@router.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: CallbackQuery):
    """
    Возврат в главное меню
    """
    user_id = callback.from_user.id
    logger.info(f"🏠 Пользователь {user_id} вернулся в меню")
    
    from src.bot.handlers.start_handler import cmd_start
    
    # Формируем fake Message для совместимости с cmd_start
    await cmd_start(callback.message)
    await callback.answer()
