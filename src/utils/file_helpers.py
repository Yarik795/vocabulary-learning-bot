"""
Утилиты для работы с файловой системой: сохранение/загрузка JSON, управление сессиями
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import DATA_DIR


logger = logging.getLogger(__name__)

# Директория для временных сессий пользователей
TEMP_SESSIONS_DIR = DATA_DIR / "temp_sessions"
SESSION_TIMEOUT = 3600  # 1 час


# ============================================================================
# РАБОТА С JSON ФАЙЛАМИ
# ============================================================================

def save_json(filepath: Path, data: Any) -> bool:
    """
    Сохранить данные в JSON файл с обработкой ошибок
    
    Args:
        filepath: Путь к файлу
        data: Данные для сохранения
        
    Returns:
        True если успешно, False если ошибка
    """
    try:
        # Создаем папку если её нет
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"💾 JSON сохранен: {filepath}")
        return True
    
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении JSON: {e}")
        return False


def load_json(filepath: Path, default: Optional[Any] = None) -> Any:
    """
    Загрузить данные из JSON файла с обработкой ошибок
    
    Args:
        filepath: Путь к файлу
        default: Значение по умолчанию если файл не существует
        
    Returns:
        Загруженные данные или default если файл не найден
    """
    try:
        if not filepath.exists():
            logger.debug(f"⚠️ JSON файл не найден: {filepath}")
            return default
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.debug(f"📖 JSON загружен: {filepath}")
        return data
    
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка при парсинге JSON {filepath}: {e}")
        return default
    
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке JSON: {e}")
        return default


# ============================================================================
# УПРАВЛЕНИЕ СЕССИЯМИ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================================

def ensure_sessions_directory():
    """
    Создать директорию для сессий если её нет
    """
    TEMP_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug(f"✅ Директория сессий проверена: {TEMP_SESSIONS_DIR}")


def save_user_session(user_id: int, session_data: Dict[str, Any]) -> bool:
    """
    Сохранить сессию пользователя в JSON файл
    
    Args:
        user_id: ID пользователя в Telegram
        session_data: Данные сессии (слова, timestamp и т.д.)
        
    Returns:
        True если успешно, False если ошибка
    """
    ensure_sessions_directory()
    
    # Добавляем timestamp для отслеживания TTL
    session_data['timestamp'] = time.time()
    
    session_file = TEMP_SESSIONS_DIR / f"{user_id}.json"
    return save_json(session_file, session_data)


def load_user_session(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Загрузить сессию пользователя из JSON файла с проверкой TTL
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        Данные сессии если существует и не истекла, иначе None
    """
    ensure_sessions_directory()
    
    session_file = TEMP_SESSIONS_DIR / f"{user_id}.json"
    session_data = load_json(session_file, default=None)
    
    if session_data is None:
        return None
    
    # Проверяем TTL (время жизни сессии)
    timestamp = session_data.get('timestamp', 0)
    if time.time() - timestamp > SESSION_TIMEOUT:
        logger.info(f"⏱️ Сессия пользователя {user_id} истекла (старше {SESSION_TIMEOUT} сек)")
        delete_user_session(user_id)
        return None
    
    logger.info(f"✅ Сессия пользователя {user_id} загружена (возраст: {time.time() - timestamp:.0f} сек)")
    return session_data


def delete_user_session(user_id: int) -> bool:
    """
    Удалить сессию пользователя
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        True если успешно, False если ошибка
    """
    session_file = TEMP_SESSIONS_DIR / f"{user_id}.json"
    
    try:
        if session_file.exists():
            session_file.unlink()
            logger.info(f"🗑️ Сессия пользователя {user_id} удалена")
            return True
        return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении сессии: {e}")
        return False


def cleanup_expired_sessions() -> int:
    """
    Удалить все истёкшие сессии (для чистоты файловой системы)
    
    Returns:
        Количество удалённых сессий
    """
    ensure_sessions_directory()
    
    deleted_count = 0
    current_time = time.time()
    
    try:
        for session_file in TEMP_SESSIONS_DIR.glob("*.json"):
            try:
                session_data = load_json(session_file, default=None)
                if session_data:
                    timestamp = session_data.get('timestamp', 0)
                    if current_time - timestamp > SESSION_TIMEOUT:
                        session_file.unlink()
                        deleted_count += 1
                        logger.debug(f"🗑️ Удалена истёкшая сессия: {session_file.name}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при проверке сессии {session_file.name}: {e}")
        
        if deleted_count > 0:
            logger.info(f"✅ Удалено {deleted_count} истёкших сессий")
        
        return deleted_count
    
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке сессий: {e}")
        return 0


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def generate_unique_id() -> str:
    """
    Генерировать уникальный ID (для словарей и т.д.)
    
    Returns:
        Уникальный ID на основе timestamp
    """
    import uuid
    return str(uuid.uuid4())[:8]


def ensure_user_directories(user_id: int):
    """
    Создать структуру папок для пользователя
    
    Args:
        user_id: ID пользователя
    """
    user_dir = DATA_DIR / "users" / str(user_id)
    dictionaries_dir = user_dir / "dictionaries"
    sessions_dir = user_dir / "sessions"
    
    dictionaries_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    
    logger.debug(f"✅ Папки пользователя {user_id} созданы")
