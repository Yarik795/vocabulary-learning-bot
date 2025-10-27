"""
Главная точка входа Telegram-бота для изучения словарных слов
"""

import logging
import asyncio
import sys
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

# ============================================================================
# НАСТРОЙКА КОДИРОВКИ ДЛЯ WINDOWS
# ============================================================================
# Устанавливаем UTF-8 кодировку для вывода на консоль Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Попытаемся установить UTF-8 для stdout (Python 3.7+)
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass  # Если не получилось, продолжаем дальше

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import (
    TELEGRAM_BOT_TOKEN, 
    DATA_DIR, 
    AUDIO_CACHE_DIR, 
    VARIANTS_CACHE_DIR,
    LOGS_DIR,
    LOG_FILE,
    LOG_LEVEL,
    LOG_FORMAT,
    CLEAR_LOGS_ON_START,
    MAX_LOG_SIZE,
    MAX_LOG_BACKUPS
)
from src.bot.handlers import router as handlers_router
from src.bot.handlers.tts_test_handler import init_tts_test_handler
from src.services.openrouter_client import OpenRouterClient
from src.services.tts_service import TTSService


# ============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================================

def clear_log_file():
    """
    Очистка файла логов при старте (удобно для тестирования)
    Позволяет видеть только логи текущего запуска, без старых данных
    """
    if LOG_FILE.exists():
        try:
            LOG_FILE.unlink()  # Удаление файла
            print(f"🧹 Файл логов очищен: {LOG_FILE}")
        except Exception as e:
            print(f"⚠️  Не удалось очистить логи: {e}")


def setup_logging():
    """
    Настройка логирования в файл и консоль с поддержкой ротации и очистки
    
    Поведение:
    - CLEAR_LOGS_ON_START=true (по умолчанию): Логи очищаются при старте
    - CLEAR_LOGS_ON_START=false: Используется RotatingFileHandler для ротации логов
    """
    # 🧹 Очистка логов при старте (если включено)
    if CLEAR_LOGS_ON_START:
        clear_log_file()
    
    # ============================================================================
    # ВЫБОР HANDLER'а: с ротацией или без
    # ============================================================================
    
    if CLEAR_LOGS_ON_START:
        # 📝 Разработка: простой FileHandler
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    else:
        # 🔄 Продакшен: RotatingFileHandler с автоматической ротацией
        # Когда файл достигает MAX_LOG_SIZE, он переименовывается в .1, .2, .3 и т.д.
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_LOG_SIZE,        # Размер одного файла (10 MB по умолчанию)
            backupCount=MAX_LOG_BACKUPS,  # Количество backup файлов (5 по умолчанию)
            encoding="utf-8"
        )
    
    # Создание логгера
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=LOG_FORMAT,
        handlers=[
            file_handler,
            logging.StreamHandler()
        ]
    )
    
    # Логгер для aiogram (чуть менее verbose)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("🤖 Telegram Bot для изучения словарных слов")
    logger.info("=" * 60)
    logger.info(f"📁 Логи пишутся в: {LOG_FILE}")
    
    # Информация о режиме логирования
    if CLEAR_LOGS_ON_START:
        logger.info("🧹 Режим РАЗРАБОТКИ: логи очищаются при старте")
    else:
        logger.info(f"🔄 Режим ПРОДАКШЕНА: ротация логов (max {MAX_LOG_SIZE} байт, backup: {MAX_LOG_BACKUPS})")
    
    return logger


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ ПАПОК
# ============================================================================

def init_directories():
    """
    Создание необходимых папок при старте приложения
    """
    logger = logging.getLogger(__name__)
    
    directories = [
        DATA_DIR,
        AUDIO_CACHE_DIR,
        VARIANTS_CACHE_DIR,
        LOGS_DIR,
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Папка создана/проверена: {directory}")
    
    # Создание директории для временных сессий
    from src.utils.file_helpers import cleanup_expired_sessions, TEMP_SESSIONS_DIR
    TEMP_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ Папка создана/проверена: {TEMP_SESSIONS_DIR}")
    
    # Очистка истёкших сессий при старте
    deleted = cleanup_expired_sessions()
    if deleted > 0:
        logger.info(f"🧹 Очищено {deleted} истёкших сессий при старте")


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================================================

async def set_default_commands(bot: Bot):
    """
    Установка меню команд в Telegram
    """
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="test_tts", description="Тест TTS (озвучка слова)"),
        BotCommand(command="tts_cache_info", description="Информация о кэше аудио"),
        BotCommand(command="clear_tts_cache", description="Очистить кэш аудио"),
    ]
    
    await bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeDefault()
    )


async def main():
    """
    Главная функция: инициализация и запуск бота
    """
    logger = logging.getLogger(__name__)
    
    # Проверка переменных окружения
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
        raise RuntimeError("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
    
    # Создание бота и диспетчера
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    logger.info("🤖 Инициализация бота...")
    logger.info(f"🔑 Токен загружен: {TELEGRAM_BOT_TOKEN[:10]}...")
    
    # ============================================================================
    # ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ
    # ============================================================================
    
    # Инициализация OpenRouter клиента для API запросов
    openrouter_client = OpenRouterClient()
    logger.info("✅ OpenRouter клиент инициализирован")
    
    # Инициализация TTS сервиса для генерации аудио
    tts_service = TTSService()
    logger.info("✅ TTS сервис инициализирован")
    
    # Регистрация TTS test handler с инициализацией сервиса
    init_tts_test_handler(tts_service)
    logger.info("✅ TTS test handler зарегистрирован")
    
    # Регистрация роутеров (обработчиков)
    dp.include_router(handlers_router)
    logger.info("✅ Обработчики зарегистрированы")
    
    # Установка команд
    await set_default_commands(bot)
    logger.info("✅ Команды установлены")
    
    # Информация о боте
    try:
        me = await bot.get_me()
        logger.info(f"✅ Бот запущен: @{me.username} (ID: {me.id})")
    except Exception as e:
        logger.error(f"❌ Ошибка при получении информации о боте: {e}")
        raise
    
    # Запуск polling (прослушивания обновлений)
    logger.info("🚀 Начало polling... Бот готов к работе!")
    logger.info("=" * 60)
    
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    except KeyboardInterrupt:
        logger.info("⏹️  Бот остановлен пользователем")
    finally:
        await bot.session.close()
        logger.info("✅ Сессия закрыта")


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

if __name__ == "__main__":
    # ⚠️ ВАЖНО: Создаём папку логов ДО инициализации логирования
    # FileHandler не создаёт папку автоматически, поэтому нужно сделать это вручную
    from pathlib import Path
    LOGS_DIR = Path(__file__).parent / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Настройка логирования
    logger = setup_logging()
    
    # Инициализация остальных папок
    logger.info("📂 Создание необходимых папок...")
    init_directories()
    
    # Запуск бота
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        raise
