"""
Обработчик отслеживания прогресса и статистики (Этап 7)
Функции: показ общей статистики, статистика по словарям, история сессий
"""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.core.progress_tracker import ProgressTracker
from src.core.dictionary_manager import DictionaryManager
from src.utils.file_helpers import load_json
from src.bot.keyboards.keyboards import get_main_menu_keyboard
from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

router = Router(name="progress_router")

# Инициализация сервисов
progress_tracker = None
dict_manager = DictionaryManager()


def format_date(date_str: str) -> str:
    """
    Форматировать дату для отображения
    """
    try:
        if not date_str:
            return "Никогда"
        dt = datetime.fromisoformat(date_str) if isinstance(date_str, str) else date_str
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError, AttributeError):
        return "N/A"


async def show_session_history(user_id: int, callback: CallbackQuery):
    """
    Показать историю последних 10 сессий пользователя
    
    Args:
        user_id: ID пользователя
        callback: CallbackQuery
    """
    try:
        from pathlib import Path
        
        user_data_dir = DATA_DIR / "users" / str(user_id)
        sessions_dir = user_data_dir / "sessions"
        
        # === ПРОВЕРЯЕМ ЕСТЬ ЛИ СЕССИИ ===
        if not sessions_dir.exists() or not list(sessions_dir.glob("*.json")):
            # Fallback UI с кнопками вместо alert
            empty_text = """📭 **У вас ещё нет истории сессий**

Завершите первую сессию обучения, чтобы просмотреть историю и отслеживать прогресс.

Начните обучение:
1️⃣ Нажмите "📖 Мои словари"
2️⃣ Выберите словарь
3️⃣ Нажмите "🎓 Начать обучение"
4️⃣ После завершения сессии история появится здесь"""
            
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="⬅️ Назад к прогрессу", callback_data="show_progress")
            keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
            keyboard.adjust(2)
            
            await callback.message.edit_text(
                empty_text,
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )
            await callback.answer()
            logger.info(f"📭 История сессий пуста для пользователя {user_id}")
            return
        
        # Получаем последние 10 сессий
        session_files = sorted(
            sessions_dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:10]
        
        # === ФОРМИРУЕМ ОТЧЁТ ===
        history_text = """📜 **ИСТОРИЯ ПОСЛЕДНИХ 10 СЕССИЙ** 📜\n
"""
        
        for i, session_file in enumerate(session_files, 1):
            try:
                session_data = load_json(str(session_file))
                if session_data:
                    dict_name = session_data.get('dict_name', 'Неизвестный словарь')
                    started_at = session_data.get('started_at', 'N/A')
                    correct = session_data.get('correct_answers', 0)
                    incorrect = session_data.get('incorrect_answers', 0)
                    total = correct + incorrect
                    
                    success_rate = (correct / total * 100) if total > 0 else 0
                    
                    date_str = format_date(started_at)
                    
                    history_text += f"""
{i}. **{dict_name}**
   📅 {date_str}
   ✅ {correct}/{total} правильно ({success_rate:.0f}%)
"""
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при чтении сессии {session_file}: {e}")
        
        history_text += """
💡 Выбери словарь для повторного обучения"""
        
        # === КЛАВИАТУРА ===
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⬅️ Назад к прогрессу", callback_data="show_progress")
        keyboard.button(text="🏠 Меню", callback_data="back_to_menu")
        keyboard.adjust(2)
        
        await callback.message.edit_text(
            history_text,
            parse_mode="Markdown",
            reply_markup=keyboard.as_markup()
        )
        await callback.answer()
        
        logger.info(f"✅ История сессий показана пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при показе истории сессий: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# ============= CALLBACK ОБРАБОТЧИК =============

@router.callback_query(F.data == "session_history")
async def callback_session_history(callback: CallbackQuery):
    """Обработчик кнопки 'История сессий'"""
    user_id = callback.from_user.id
    logger.info(f"📜 Пользователь {user_id} открыл историю сессий")
    await show_session_history(user_id, callback)


async def show_progress_statistics(user_id: int, callback: CallbackQuery = None, message: Message = None):
    """
    Показать общую статистику прогресса пользователя
    
    Args:
        user_id: ID пользователя
        callback: CallbackQuery если вызвано из callback
        message: Message если вызвано из message
    """
    try:
        # Загружаем прогресс
        tracker = ProgressTracker(user_id)
        total_progress = tracker.get_total_progress()
        
        # Получаем список словарей пользователя
        dictionaries = dict_manager.list_dictionaries(user_id)
        
        # === КЭШИРУЕМ ПРОГРЕСС ДЛЯ ВСЕХ СЛОВАРЕЙ (ОПТИМИЗАЦИЯ N+1) ===
        dict_progress_cache = {}
        for dictionary in dictionaries:
            dict_progress_cache[dictionary.id] = tracker.get_dictionary_progress(dictionary.id)
        
        # === ФОРМИРУЕМ ОСНОВНОЕ СООБЩЕНИЕ ===
        
        stats_text = """📊 **ВАШ ПРОГРЕСС** 📊

**📚 Общая статистика:**
"""
        
        # Добавляем основные показатели
        stats_text += f"""• Пройдено сессий: {total_progress.get('total_sessions', 0)}
• Слов выучено на 5: {total_progress.get('total_words_learned', 0)}
• Всего попыток: {total_progress.get('total_attempts', 0)}
• Правильных ответов: {total_progress.get('total_correct', 0)}
• Неправильных ответов: {total_progress.get('total_incorrect', 0)}
• Процент успехов: {total_progress.get('success_rate', 0):.1f}%
"""
        
        # Добавляем информацию о последней активности
        if total_progress.get('last_activity'):
            last_activity = format_date(total_progress['last_activity'])
            stats_text += f"• Последняя активность: {last_activity}\n"
        
        # === СТАТИСТИКА ПО СЛОВАРЯМ ===
        
        if dictionaries:
            stats_text += f"\n**📖 Ваши словари ({len(dictionaries)}):**\n"
            
            for i, dictionary in enumerate(dictionaries, 1):
                # Используем кэшированные результаты (исправление N+1 запроса)
                dict_progress = dict_progress_cache[dictionary.id]
                
                words_total = dict_progress.get('total_words', 0)
                words_mastered = dict_progress.get('words_mastered', 0)
                success_rate = dict_progress.get('success_rate', 0)
                
                # Индикатор прогресса
                if words_total > 0:
                    progress_percent = (words_mastered / words_total) * 100
                    filled = int(progress_percent / 10)
                    empty = 10 - filled
                    progress_bar = "█" * filled + "░" * empty
                else:
                    progress_bar = "░░░░░░░░░░"
                    progress_percent = 0
                
                # Статус словаря
                if words_mastered == words_total and words_total > 0:
                    status = "✅ Выучено"
                else:
                    status = f"🔄 {words_mastered}/{words_total}"
                
                stats_text += f"\n{i}. 📕 **{dictionary.name}** {status}\n"
                stats_text += f"   {progress_bar} {progress_percent:.0f}%\n"
                stats_text += f"   Успешность: {success_rate:.1f}%"
                
                if dict_progress.get('last_activity'):
                    last_activity_str = format_date(dict_progress['last_activity'].isoformat() if hasattr(dict_progress['last_activity'], 'isoformat') else str(dict_progress['last_activity']))
                    stats_text += f" | Последняя активность: {last_activity_str}"
                
                if dict_progress.get('total_attempts', 0) > 0:
                    stats_text += f" ({dict_progress['total_correct']}/{dict_progress['total_attempts']})\n"
                else:
                    stats_text += "\n"
        else:
            stats_text += "\n📭 **У вас пока нет словарей**\n"
        
        stats_text += """
💡 **Совет:** Начните с создания нового словаря через загрузку фотографии!"""
        
        # === СОЗДАЁМ КЛАВИАТУРУ ===
        
        keyboard = InlineKeyboardBuilder()
        
        # Если есть словари - добавляем кнопку детальной информации
        if dictionaries:
            keyboard.button(text="📈 Детали по словарям", callback_data="progress_details")
            keyboard.button(text="📜 История сессий", callback_data="session_history")
            keyboard.adjust(2)
        
        keyboard.button(text="📚 К словарям", callback_data="view_dictionaries")
        keyboard.button(text="🏠 В меню", callback_data="back_to_menu")
        keyboard.adjust(2)
        
        # === ОТПРАВЛЯЕМ ===
        
        if callback:
            await callback.message.edit_text(
                stats_text,
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )
            await callback.answer()
        elif message:
            await message.answer(
                stats_text,
                parse_mode="Markdown",
                reply_markup=keyboard.as_markup()
            )
        
        logger.info(f"✅ Статистика прогресса показана пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при показе статистики: {e}")
        error_msg = f"❌ Ошибка при загрузке прогресса: {str(e)}"
        if callback:
            await callback.answer(error_msg, show_alert=True)
        elif message:
            await message.answer(error_msg)


async def show_dictionary_progress_details(user_id: int, callback: CallbackQuery):
    """
    Показать детальную статистику по каждому словарю
    
    Args:
        user_id: ID пользователя
        callback: CallbackQuery
    """
    try:
        tracker = ProgressTracker(user_id)
        dictionaries = dict_manager.list_dictionaries(user_id)
        
        if not dictionaries:
            await callback.answer("❌ У вас нет словарей", show_alert=True)
            return
        
        # === ФОРМИРУЕМ ПОДРОБНЫЙ ОТЧЁТ ===
        
        details_text = """📈 **ДЕТАЛЬНАЯ СТАТИСТИКА ПО СЛОВАРЯМ** 📈\n
"""
        
        for i, dictionary in enumerate(dictionaries, 1):
            dict_progress = tracker.get_dictionary_progress(dictionary.id)
            
            words_total = dict_progress.get('total_words', 0)
            words_mastered = dict_progress.get('words_mastered', 0)
            success_rate = dict_progress.get('success_rate', 0)
            total_attempts = dict_progress.get('total_attempts', 0)
            correct = dict_progress.get('total_correct', 0)
            incorrect = dict_progress.get('total_incorrect', 0)
            
            details_text += f"""
{i}. **{dictionary.name}**
   Слов выучено: {words_mastered}/{words_total}
   Попыток: {total_attempts}
   ✅ Правильных: {correct}
   ❌ Неправильных: {incorrect}
   Успешность: {success_rate:.1f}%
   Статус: {'✅ ПОЛНОСТЬЮ ВЫУЧЕНО' if words_mastered == words_total and words_total > 0 else '🔄 В ПРОЦЕССЕ'}
"""
        
        details_text += "\n💡 Продолжайте учить слова для повышения процента успешности!"
        
        # === КЛАВИАТУРА ===
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⬅️ Назад", callback_data="show_progress")
        keyboard.button(text="🏠 Меню", callback_data="back_to_menu")
        keyboard.adjust(2)
        
        await callback.message.edit_text(
            details_text,
            parse_mode="Markdown",
            reply_markup=keyboard.as_markup()
        )
        await callback.answer()
        
        logger.info(f"✅ Детальная статистика показана пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при показе деталей: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# ============================================================================
# CALLBACK ОБРАБОТЧИКИ
# ============================================================================

@router.callback_query(F.data == "show_progress")
async def callback_show_progress(callback: CallbackQuery):
    """Обработчик кнопки 'Мой прогресс'"""
    user_id = callback.from_user.id
    logger.info(f"📊 Пользователь {user_id} открыл прогресс")
    await show_progress_statistics(user_id, callback=callback)


@router.callback_query(F.data == "progress_details")
async def callback_progress_details(callback: CallbackQuery):
    """Обработчик кнопки 'Детали по словарям'"""
    user_id = callback.from_user.id
    logger.info(f"📈 Пользователь {user_id} открыл детали прогресса")
    await show_dictionary_progress_details(user_id, callback)


@router.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: CallbackQuery):
    """Обработчик кнопки 'В меню'"""
    user_id = callback.from_user.id
    logger.info(f"🏠 Пользователь {user_id} вернулся в меню")
    
    welcome_text = """🏠 **ГЛАВНОЕ МЕНЮ**

Выберите действие:
📸 Загрузить новое фото со словами
📖 Просмотреть свои словари
📊 Посмотреть прогресс обучения
❓ Получить справку"""
    
    await callback.message.edit_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()
