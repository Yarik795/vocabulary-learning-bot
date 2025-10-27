"""
Persistence слой для сохранения и восстановления сессий обучения на диск (Этап 8)
ПРОБЛЕМА #7: Сессии сохраняются на диск для восстановления при перезагрузке бота
"""

import logging
import json
from pathlib import Path
from typing import Optional
from src.core.learning_session import LearningSession
from src.utils.file_helpers import save_json, load_json
from config.settings import DATA_DIR

logger = logging.getLogger(__name__)


class SessionPersistence:
    """Управление сохранением и восстановлением сессий обучения"""
    
    SESSIONS_DIR = DATA_DIR / "temp_sessions"
    
    @classmethod
    def _ensure_dir(cls):
        """Создать директорию для сессий если её нет"""
        cls.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    async def save_session(cls, user_id: int, session: LearningSession) -> bool:
        """
        Сохранить сессию обучения на диск
        
        Args:
            user_id: ID пользователя
            session: Объект LearningSession для сохранения
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            cls._ensure_dir()
            
            session_file = cls.SESSIONS_DIR / f"{user_id}_{session.session_id}.json"
            
            # Конвертируем сессию в JSON
            session_data = {
                'user_id': user_id,
                'session_id': session.session_id,
                'dict_id': session.dict_id,
                'dict_name': session.dict_name,
                'words_list': list(session.words.keys()),           # ✅ Используем существующие ключи
                'current_word': session.current_word,              # ✅ Исправлено: current_word_index → current_word
                'stats': session.stats.model_dump(mode='json') if hasattr(session.stats, 'model_dump') else session.stats.__dict__,
                'words_stats': {                                   # ✅ Вместо words_progress берём из Word объектов
                    word: {
                        'correct_count': word_obj.correct_count,
                        'incorrect_count': word_obj.incorrect_count,
                        'total_attempts': word_obj.total_attempts,
                        'times_mastered': word_obj.times_mastered,
                        'is_mastered': word_obj.is_mastered,
                        'last_attempted': word_obj.last_attempted.isoformat() if hasattr(word_obj, 'last_attempted') and word_obj.last_attempted else None
                    }
                    for word, word_obj in session.words.items()
                }
            }
            
            save_json(str(session_file), session_data)
            logger.info(f"💾 Сессия {session.session_id} сохранена на диск для пользователя {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении сессии на диск: {e}")
            return False
    
    @classmethod
    async def load_session(cls, user_id: int, session_id: str) -> Optional[LearningSession]:
        """
        Загрузить сессию обучения с диска
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии для загрузки
            
        Returns:
            LearningSession объект или None если не найдена
        """
        try:
            cls._ensure_dir()
            
            session_file = cls.SESSIONS_DIR / f"{user_id}_{session_id}.json"
            
            if not session_file.exists():
                logger.warning(f"⚠️ Файл сессии не найден: {session_file}")
                return None
            
            session_data = load_json(str(session_file))
            
            # Восстанавливаем сессию
            session = LearningSession(
                user_id=session_data['user_id'],
                dict_id=session_data['dict_id'],
                dict_name=session_data['dict_name'],
                words_list=session_data['words_list']
            )
            
            session.session_id = session_data['session_id']
            session.current_word = session_data.get('current_word')  # ✅ Исправлено: current_word_index → current_word
            
            # Восстанавливаем прогресс слов из words_stats
            if 'words_stats' in session_data:  # ✅ Ищем words_stats вместо words_progress
                for word, stats_data in session_data['words_stats'].items():
                    if word in session.words:
                        word_obj = session.words[word]
                        word_obj.correct_count = stats_data.get('correct_count', 0)
                        word_obj.incorrect_count = stats_data.get('incorrect_count', 0)
                        word_obj.total_attempts = stats_data.get('total_attempts', 0)
                        word_obj.times_mastered = stats_data.get('times_mastered', 0)
                        word_obj.is_mastered = stats_data.get('is_mastered', False)
            
            logger.info(f"📂 Сессия {session_id} загружена с диска для пользователя {user_id}")
            return session
            
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке сессии с диска: {e}")
            return None
    
    @classmethod
    async def delete_session(cls, user_id: int, session_id: str) -> bool:
        """
        Удалить сохранённую сессию с диска
        
        Args:
            user_id: ID пользователя
            session_id: ID сессии для удаления
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            session_file = cls.SESSIONS_DIR / f"{user_id}_{session_id}.json"
            
            if session_file.exists():
                session_file.unlink()
                logger.info(f"🗑️ Сессия {session_id} удалена с диска для пользователя {user_id}")
                return True
            else:
                logger.warning(f"⚠️ Файл сессии не найден для удаления: {session_file}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении сессии с диска: {e}")
            return False
    
    @classmethod
    async def load_all_sessions_for_user(cls, user_id: int) -> dict:
        """
        Загрузить все сохранённые сессии для пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Словарь {session_id: LearningSession} найденных сессий
        """
        try:
            cls._ensure_dir()
            
            sessions = {}
            pattern = f"{user_id}_*.json"
            
            for session_file in cls.SESSIONS_DIR.glob(pattern):
                try:
                    session_data = load_json(str(session_file))
                    session_id = session_data.get('session_id')
                    
                    if session_id:
                        session = await cls.load_session(user_id, session_id)
                        if session:
                            sessions[session_id] = session
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при загрузке сессии {session_file}: {e}")
                    continue
            
            logger.info(f"📂 Загружено {len(sessions)} сохранённых сессий для пользователя {user_id}")
            return sessions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке всех сессий: {e}")
            return {}
