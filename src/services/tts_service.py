"""
Сервис для генерации аудио (Text-to-Speech) словарных слов
Интеграция с gTTS (Google Text-to-Speech) + кэширование аудио
"""

import logging
import hashlib
from pathlib import Path
from typing import Optional
import asyncio
import tempfile

from config.settings import AUDIO_CACHE_DIR
from config.models import TTS_MODEL_CONFIG
from gtts import gTTS

logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE = 10 * 1024 * 1024 # 10 MB


class TTSService:
    """
    Сервис для генерации и кэширования аудио произношения слов
    """
    
    def __init__(self):
        """
        Инициализация TTS сервиса с gTTS
        """
        self.cache_dir = AUDIO_CACHE_DIR
        self.lang = TTS_MODEL_CONFIG.get("voice", "ru")  # Язык для gTTS
        self.slow = TTS_MODEL_CONFIG.get("slow", False)  # Нормальная скорость речи
        
        # Создание папки кэша если не существует
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ TTSService инициализирован (язык: {self.lang}, кэш: {self.cache_dir})")
    
    def _get_word_hash(self, word: str) -> str:
        """
        Генерация хеша для имени файла кэша
        
        Args:
            word: Словарное слово
            
        Returns:
            Хеш слова (8 первых символов)
        """
        word_lower = word.lower().strip()
        word_hash = hashlib.md5(word_lower.encode()).hexdigest()[:8]
        return word_hash
    
    def _get_cache_path(self, word: str) -> Path:
        """
        Получить путь к файлу кэша для слова
        
        Args:
            word: Словарное слово
            
        Returns:
            Полный путь к файлу кэша
        """
        word_hash = self._get_word_hash(word)
        return self.cache_dir / f"{word_hash}.mp3"
    
    def get_cached_audio(self, word: str) -> Optional[bytes]:
        """
        Получить аудио из кэша если существует
        
        Args:
            word: Словарное слово
            
        Returns:
            Аудиофайл в формате bytes или None если нет в кэше
        """
        cache_path = self._get_cache_path(word)
        
        if cache_path.exists():
            try:
                audio_bytes = cache_path.read_bytes()
                logger.info(f"📦 Аудио для '{word}' получено из кэша ({len(audio_bytes)} байт)")
                return audio_bytes
            except Exception as e:
                logger.error(f"❌ Ошибка при чтении кэша для '{word}': {e}")
                return None
        
        logger.debug(f"📭 Аудио для '{word}' не найдено в кэше")
        return None
    
    def save_to_cache(self, word: str, audio_bytes: bytes) -> bool:
        """
        Сохранить аудио в кэш
        
        Args:
            word: Словарное слово
            audio_bytes: Аудиофайл в формате bytes
            
        Returns:
            True если успешно сохранено, False если ошибка
        """
        cache_path = self._get_cache_path(word)
        
        if len(audio_bytes) > MAX_AUDIO_SIZE:
            logger.warning(f"⚠️ Аудио для '{word}' слишком большое ({len(audio_bytes)} байт), не будет сохранено.")
            return False

        try:
            cache_path.write_bytes(audio_bytes)
            logger.info(f"💾 Аудио для '{word}' сохранено в кэш ({len(audio_bytes)} байт)")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении аудио в кэш для '{word}': {e}")
            return False
    
    async def generate_audio(self, word: str) -> Optional[bytes]:
        """
        Генерация или получение аудио для слова
        
        Алгоритм:
        1. Проверка кэша - если есть, возвращаем готовое аудио
        2. Если нет в кэше - генерация через gTTS
        3. Сохранение в кэш
        4. Возврат аудио
        
        Args:
            word: Словарное слово для озвучивания
            
        Returns:
            Аудиофайл в формате bytes или None при ошибке
        """
        logger.info(f"🔊 Генерация аудио для слова '{word}'")
        
        # Шаг 1: Проверка кэша
        cached_audio = self.get_cached_audio(word)
        if cached_audio:
            return cached_audio
        
        # Шаг 2: Генерация аудио через gTTS
        try:
            # Используем временный файл для сохранения MP3 с gTTS
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_path = tmp_file.name
            
            try:
                # Генерируем аудио через gTTS
                tts = gTTS(text=word, lang=self.lang, slow=self.slow)
                tts.save(tmp_path)
                
                # Читаем аудиофайл
                audio_bytes = Path(tmp_path).read_bytes()
                
                # Шаг 3: Сохранение в кэш
                self.save_to_cache(word, audio_bytes)
                
                logger.info(f"✅ Аудио для '{word}' успешно сгенерировано ({len(audio_bytes)} байт)")
                return audio_bytes
            
            finally:
                # Удаляем временный файл
                temp_path_obj = Path(tmp_path)
                if temp_path_obj.exists():
                    temp_path_obj.unlink()
        
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации аудио для '{word}': {e}")
            return None
    
    async def batch_generate_audio(self, words: list) -> dict:
        """
        Генерация аудио для списка слов
        Слова из кэша получаются последовательно (быстро), но новые генерируются параллельно
        
        Args:
            words: Список слов для озвучивания
            
        Returns:
            Словарь {слово: аудио_bytes или None при ошибке}
        """
        logger.info(f"🔊 Batch-генерация аудио для {len(words)} слов (параллельная обработка)")
        
        results = {}
        cached_count = 0
        words_to_generate = []  # Слова, которые нужно сгенерировать
        words_positions = {}  # Для сохранения позиции слова
        
        # Шаг 1: Проверяем кэш для всех слов
        for word in words:
            cached_audio = self.get_cached_audio(word)
            if cached_audio:
                results[word] = cached_audio
                cached_count += 1
            else:
                words_to_generate.append(word)
                words_positions[word] = len(results)
        
        logger.info(f"📦 Найдено в кэше: {cached_count}, требуется генерация: {len(words_to_generate)}")
        
        # Шаг 2: Генерируем новые аудио параллельно
        if words_to_generate:
            generate_tasks = [
                self.generate_audio(word) for word in words_to_generate
            ]
            generated_audios = await asyncio.gather(*generate_tasks, return_exceptions=True)
            
            generated_count = 0
            failed_count = 0
            
            for word, audio in zip(words_to_generate, generated_audios):
                if isinstance(audio, Exception):
                    logger.error(f"❌ Ошибка при генерации аудио для '{word}': {audio}")
                    results[word] = None
                    failed_count += 1
                elif audio is not None:
                    results[word] = audio
                    generated_count += 1
                else:
                    results[word] = None
                    failed_count += 1
        else:
            generated_count = 0
            failed_count = 0
        
        logger.info(
            f"✅ Batch-генерация завершена: "
            f"{generated_count} новых, "
            f"{cached_count} из кэша, "
            f"{failed_count} ошибок"
        )
        
        return results
    
    def clear_cache(self) -> bool:
        """
        Очистить весь кэш аудио
        
        Returns:
            True если успешно, False если ошибка
        """
        try:
            import shutil
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ Кэш аудио очищен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке кэша: {e}")
            return False
    
    def get_cache_info(self) -> dict:
        """
        Получить информацию о текущем кэше
        
        Returns:
            Словарь с информацией о кэше
        """
        if not self.cache_dir.exists():
            return {"total_files": 0, "total_size_mb": 0}
        
        total_files = len(list(self.cache_dir.glob("*.mp3")))
        total_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.mp3"))
        
        return {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir)
        }
