"""
Менеджер для управления словарями пользователя (CRUD операции)
Сохранение в файловой системе: data/users/{user_id}/dictionaries/
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

from config.settings import DATA_DIR
from src.core.models import Dictionary
from src.utils.file_helpers import save_json, load_json, generate_unique_id, ensure_user_directories

logger = logging.getLogger(__name__)


class DictionaryManager:
    """
    Менеджер словарей пользователя
    Операции: создание, чтение, обновление, удаление, список
    """
    
    def __init__(self):
        """Инициализация менеджера"""
        self.base_data_dir = DATA_DIR
    
    
    def _get_user_dictionaries_dir(self, user_id: int) -> Path:
        """
        Получить директорию словарей пользователя
        
        Args:
            user_id: ID пользователя в Telegram
            
        Returns:
            Path к директории словарей пользователя
        """
        return self.base_data_dir / "users" / str(user_id) / "dictionaries"
    
    
    def _get_dictionary_filepath(self, user_id: int, dict_id: str) -> Path:
        """
        Получить путь к файлу словаря
        
        Args:
            user_id: ID пользователя
            dict_id: ID словаря
            
        Returns:
            Path к файлу словаря
        """
        return self._get_user_dictionaries_dir(user_id) / f"{dict_id}.json"
    
    
    def create_dictionary(self, user_id: int, words: List[str], name: Optional[str] = None) -> Optional[Dictionary]:
        """
        Создать новый словарь
        
        Args:
            user_id: ID пользователя
            words: Список слов
            name: Название словаря (опционально)
            
        Returns:
            Объект Dictionary если успешно, None если ошибка
        """
        try:
            # Создаём папку пользователя если её нет
            ensure_user_directories(user_id)
            
            # Генерируем уникальный ID для словаря
            dict_id = generate_unique_id()
            
            # === КАПИТАЛИЗАЦИЯ ПЕРВЫХ БУКВ СЛОВ ===
            capitalized_words = [word.capitalize() if word else word for word in words]
            
            # Генерируем название если не передано
            if not name:
                dict_count = len(self.list_dictionaries(user_id))
                name = f"Словарь #{dict_count + 1}"
            
            # Создаём объект словаря
            dictionary = Dictionary(
                id=dict_id,
                name=name,
                words=capitalized_words,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Сохраняем в файл
            filepath = self._get_dictionary_filepath(user_id, dict_id)
            dict_data = dictionary.model_dump(mode='json')
            
            if save_json(filepath, dict_data):
                logger.info(f"✅ Словарь создан: пользователь {user_id}, ID {dict_id}, слов: {len(capitalized_words)}")
                return dictionary
            else:
                logger.error(f"❌ Ошибка при сохранении словаря {dict_id}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка при создании словаря: {e}")
            return None
    
    
    def get_dictionary(self, user_id: int, dict_id: str) -> Optional[Dictionary]:
        """
        Получить словарь по ID
        
        Args:
            user_id: ID пользователя
            dict_id: ID словаря
            
        Returns:
            Объект Dictionary если найден, None иначе
        """
        try:
            filepath = self._get_dictionary_filepath(user_id, dict_id)
            data = load_json(filepath, default=None)
            
            if data:
                dictionary = Dictionary(**data)
                logger.debug(f"✅ Словарь загружен: {dict_id}")
                return dictionary
            else:
                logger.warning(f"⚠️ Словарь не найден: {dict_id}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке словаря {dict_id}: {e}")
            return None
    
    
    def update_dictionary(self, user_id: int, dict_id: str, words: List[str], name: Optional[str] = None) -> bool:
        """
        Обновить словарь
        
        Args:
            user_id: ID пользователя
            dict_id: ID словаря
            words: Новый список слов
            name: Новое название (опционально)
            
        Returns:
            True если успешно, False иначе
        """
        try:
            # Получаем существующий словарь
            dictionary = self.get_dictionary(user_id, dict_id)
            if not dictionary:
                logger.error(f"❌ Словарь {dict_id} не найден")
                return False
            
            # === КАПИТАЛИЗАЦИЯ ПЕРВЫХ БУКВ СЛОВ ===
            capitalized_words = [word.capitalize() if word else word for word in words]
            
            # Обновляем данные
            dictionary.words = capitalized_words
            if name:
                dictionary.name = name
            dictionary.updated_at = datetime.now()
            
            # Сохраняем обновлённый словарь
            filepath = self._get_dictionary_filepath(user_id, dict_id)
            dict_data = dictionary.model_dump(mode='json')
            
            if save_json(filepath, dict_data):
                logger.info(f"✅ Словарь обновлен: {dict_id}, слов: {len(capitalized_words)}")
                return True
            else:
                logger.error(f"❌ Ошибка при обновлении словаря {dict_id}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении словаря {dict_id}: {e}")
            return False
    
    
    def delete_dictionary(self, user_id: int, dict_id: str) -> bool:
        """
        Удалить словарь
        
        Args:
            user_id: ID пользователя
            dict_id: ID словаря
            
        Returns:
            True если успешно, False иначе
        """
        try:
            filepath = self._get_dictionary_filepath(user_id, dict_id)
            
            if filepath.exists():
                filepath.unlink()
                logger.info(f"🗑️ Словарь удалён: {dict_id}")
                return True
            else:
                logger.warning(f"⚠️ Словарь {dict_id} не найден при удалении")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении словаря {dict_id}: {e}")
            return False
    
    
    def list_dictionaries(self, user_id: int) -> List[Dictionary]:
        """
        Получить список всех словарей пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список объектов Dictionary
        """
        try:
            user_dict_dir = self._get_user_dictionaries_dir(user_id)
            
            if not user_dict_dir.exists():
                logger.debug(f"ℹ️ У пользователя {user_id} нет словарей (папка не существует)")
                return []
            
            dictionaries = []
            
            # Читаем все JSON файлы из директории
            for dict_file in user_dict_dir.glob("*.json"):
                try:
                    data = load_json(dict_file, default=None)
                    if data:
                        dictionary = Dictionary(**data)
                        dictionaries.append(dictionary)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при загрузке словаря из {dict_file}: {e}")
            
            # Сортируем по дате создания (новые первыми)
            dictionaries.sort(key=lambda d: d.created_at, reverse=True)
            
            logger.debug(f"✅ Загружено {len(dictionaries)} словарей для пользователя {user_id}")
            return dictionaries
        
        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка словарей пользователя {user_id}: {e}")
            return []
    
    
    def dictionary_exists(self, user_id: int, dict_id: str) -> bool:
        """
        Проверить существование словаря
        
        Args:
            user_id: ID пользователя
            dict_id: ID словаря
            
        Returns:
            True если словарь существует, False иначе
        """
        filepath = self._get_dictionary_filepath(user_id, dict_id)
        return filepath.exists()
    
    
    def get_word_count(self, user_id: int, dict_id: str) -> int:
        """
        Получить количество слов в словаре
        
        Args:
            user_id: ID пользователя
            dict_id: ID словаря
            
        Returns:
            Количество слов
        """
        dictionary = self.get_dictionary(user_id, dict_id)
        if dictionary:
            return len(dictionary.words)
        return 0
    
    
    def get_total_words(self, user_id: int) -> int:
        """
        Получить общее количество слов во всех словарях пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Общее количество слов
        """
        dictionaries = self.list_dictionaries(user_id)
        return sum(len(d.words) for d in dictionaries)
