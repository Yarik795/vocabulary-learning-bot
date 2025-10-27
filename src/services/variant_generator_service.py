"""
Сервис для batch-генерации неправильных вариантов написания слов
Интегрирует OpenRouter API для LLM запросов и управляет кэшированием вариантов
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from config.settings import VARIANTS_CACHE_DIR, VARIANTS_COUNT
from config.models import VARIANT_GENERATION_MODEL
from config.prompts import (
    get_variant_generation_batch_prompt,
    get_variant_generation_single_prompt,
    VARIANT_GENERATION_SYSTEM_PROMPT
)
from src.services.openrouter_client import OpenRouterClient
from src.utils.file_helpers import save_json, load_json
from src.utils.word_helpers import (
    get_word_hash,
    get_words_hashes,
    validate_variant_structure,
    is_russian_word
)


logger = logging.getLogger(__name__)


class VariantGeneratorService:
    """
    Сервис для генерации неправильных вариантов написания слов
    
    Поддерживает:
    - Batch-генерацию для списка слов (основной режим)
    - Fallback генерацию для одного слова
    - Кэширование результатов в data/variants_cache/
    - Выбор вариантов по уровню сложности во время обучения
    """
    
    def __init__(self):
        """Инициализация сервиса"""
        self.client = OpenRouterClient()
        self.cache_dir = VARIANTS_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ VariantGeneratorService инициализирован")
        logger.info(f"   Кэш директория: {self.cache_dir}")
    
    # ========================================================================
    # BATCH-ГЕНЕРАЦИЯ ВАРИАНТОВ (основной режим)
    # ========================================================================
    
    async def generate_variants_batch(self, words_list: List[str]) -> Dict[str, Dict]:
        """
        Batch-генерация вариантов для списка слов одним запросом к LLM
        
        Алгоритм:
        1. Проверка кэша для всех слов
        2. Разделение на cached_words и uncached_words
        3. Batch-запрос к OpenRouter для uncached_words
        4. Парсинг и валидация ответа
        5. Сохранение в кэш (по файлу на слово)
        6. Возврат результата
        
        Args:
            words_list: Список слов для генерации вариантов
            
        Returns:
            Словарь {слово: {easy: [...], medium: [...], hard: [...]}}
        """
        logger.info(f"🔄 BATCH-генерация вариантов для {len(words_list)} слов")
        
        if not words_list:
            logger.warning("⚠️ Пустой список слов")
            return {}
        
        # Шаг 1: Проверка кэша для всех слов
        logger.debug(f"🔍 Проверка кэша для всех слов...")
        cached_variants = self._load_cached_variants(words_list)
        cached_words = set(cached_variants.keys())
        uncached_words = [w for w in words_list if w not in cached_words]
        
        logger.debug(f"   📊 Всего слов: {len(words_list)}")
        logger.debug(f"   ✅ Из кэша: {len(cached_words)}")
        logger.debug(f"   ⏳ Нужна генерация: {len(uncached_words)}")
        
        # Если все из кэша
        if not uncached_words:
            logger.info(f"✅ Все варианты уже в кэше! Возвращаю из кэша...")
            return cached_variants
        
        # Шаг 2-3: Batch-запрос к OpenRouter для uncached_words
        logger.info(f"📤 Отправляю batch-запрос для {len(uncached_words)} слов...")
        batch_response = await self._request_batch_variants(uncached_words)
        
        if not batch_response:
            logger.error(f"❌ Batch-запрос вернул пустой результат")
            # Используем алгоритмическую генерацию как fallback
            logger.info(f"🔧 Используем алгоритмическую генерацию для {len(uncached_words)} слов...")
            for word in uncached_words:
                try:
                    variants = self._algorithmic_generation(word)
                    if variants:
                        self._save_variants_to_cache(word, variants)
                        logger.info(f"✅ Алгоритмическая генерация для '{word}'")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при алгоритмической генерации '{word}': {e}")
            
            # Загружаем алгоритмически сгенерированные варианты
            cached_variants.update(self._load_cached_variants(uncached_words))
            logger.info(f"✅ Алгоритмическая генерация завершена! Вариантов: {len(cached_variants)}")
            return cached_variants
        
        # Шаг 4: Парсинг и валидация
        logger.debug(f"🔍 Парсинг и валидация batch-ответа...")
        parsed_variants, validation_errors = self._parse_and_validate_batch_response(
            batch_response, uncached_words
        )
        
        # Если были ошибки валидации - fallback
        if validation_errors:
            logger.warning(f"⚠️ Ошибки при валидации {len(validation_errors)} слов: {validation_errors}")
            await self._fallback_generation_for_failed_words(validation_errors)
            # Загружаем только те варианты, которые успешно были сгенерированы в fallback
            fallback_variants = self._load_cached_variants(validation_errors)
            if fallback_variants:
                parsed_variants.update(fallback_variants)
                logger.info(f"✅ Fallback восстановил {len(fallback_variants)} слов")
            else:
                logger.warning(f"⚠️ Fallback не дал результатов для {len(validation_errors)} слов")
        
        # Шаг 5: Сохранение в кэш
        logger.debug(f"💾 Сохранение вариантов в кэш...")
        for word, variants in parsed_variants.items():
            self._save_variants_to_cache(word, variants)
        
        logger.info(f"✅ Успешно сгенерировано вариантов для {len(parsed_variants)} слов")
        
        # Шаг 6: Комбинируем с уже закэшированными
        result = {**cached_variants, **parsed_variants}
        
        logger.info(f"✅ Batch-генерация завершена! Всего вариантов: {len(result)}")
        return result
    
    # ========================================================================
    # ЗАПРОС К LLM
    # ========================================================================
    
    async def _request_batch_variants(self, words_list: List[str]) -> Optional[str]:
        """
        Batch-запрос к OpenRouter для генерации вариантов
        
        Args:
            words_list: Список слов для генерации
            
        Returns:
            JSON строка с вариантами или None при ошибке
        """
        try:
            # Формируем промпт
            user_prompt = get_variant_generation_batch_prompt(words_list)
            
            logger.debug(f"📝 Промпт длина: {len(user_prompt)} символов")
            logger.debug(f"📝 Первые 200 символов промпта: {user_prompt[:200]}...")
            
            # Формируем messages для chat_completion
            messages = [
                {
                    "role": "system",
                    "content": VARIANT_GENERATION_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            # Запрос к OpenRouter
            logger.info(f"🔄 Отправляю запрос к {VARIANT_GENERATION_MODEL}...")
            response = await self.client.chat_completion(
                messages=messages,
                model=VARIANT_GENERATION_MODEL,
                temperature=0.7,
                max_tokens=1000 + len(words_list) * 100  # Динамически зависит от количества слов
            )
            
            logger.debug(f"✅ Получен ответ ({len(response)} символов)")
            logger.info(f"📄 API ответ (первые 300 символов):\n{response[:300]}")
            return response
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Ошибка при batch-запросе: {e}")
            
            # Проверяем если это ошибка 403 (доступ запрещен)
            if "403" in error_msg:
                logger.warning(f"⚠️ Ошибка 403 при работе с {VARIANT_GENERATION_MODEL}")
                logger.warning(f"   Пробую резервную модель: {VARIANT_GENERATION_MODEL}")
                
                # Пробуем fallback модель
                from config.models import FALLBACK_MODEL
                logger.info(f"🔄 Переключаюсь на резервную модель {FALLBACK_MODEL}...")
                
                try:
                    response = await self.client.chat_completion(
                        messages=messages,
                        model=FALLBACK_MODEL,
                        temperature=0.7,
                        max_tokens=1000 + len(words_list) * 100
                    )
                    logger.info(f"✅ Резервная модель работает! Получен ответ ({len(response)} символов)")
                    return response
                
                except Exception as fallback_error:
                    logger.error(f"❌ Ошибка и при резервной модели: {fallback_error}")
                    logger.info(f"🔄 Пробую алгоритмическую генерацию для {len(words_list)} слов...")
                    # Последний resort - используем алгоритмическую генерацию
                    return None
            
            return None
    
    # ========================================================================
    # ПАРСИНГ И ВАЛИДАЦИЯ
    # ========================================================================
    
    def _parse_and_validate_batch_response(
        self,
        response_text: str,
        words_list: List[str]
    ) -> Tuple[Dict, List[str]]:
        """
        Парсинг и валидация batch-ответа от LLM
        
        Args:
            response_text: JSON текст с вариантами
            words_list: Исходный список слов (для проверки)
            
        Returns:
            (успешные_варианты: {слово: [...]}, ошибки: [слова])
        """
        parsed_variants = {}
        error_words = []
        
        try:
            # Парсинг JSON
            logger.debug(f"🔍 Парсинг JSON ответа...")
            # Ищем JSON в ответе (иногда LLM добавляет текст вокруг)
            json_text = self._extract_json_from_response(response_text)
            response_dict = json.loads(json_text)
            
            logger.debug(f"✅ JSON спаршен, найдено слов в ответе: {len(response_dict)}")
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            logger.debug(f"   Первые 500 символов ответа: {response_text[:500]}")
            return {}, words_list
        
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге ответа: {e}")
            return {}, words_list
        
        # Валидация каждого слова
        for word in words_list:
            if word not in response_dict:
                logger.warning(f"⚠️ Слово '{word}' отсутствует в ответе LLM")
                error_words.append(word)
                continue
            
            variants_list = response_dict[word]
            
            # Проверяем что это список
            if not isinstance(variants_list, list):
                logger.warning(f"⚠️ Варианты для '{word}' должны быть списком, получено: {type(variants_list)}")
                error_words.append(word)
                continue
            
            # Проверяем количество вариантов
            if len(variants_list) != VARIANTS_COUNT:
                logger.warning(f"⚠️ Неверное количество вариантов для '{word}': {len(variants_list)}, ожидается {VARIANTS_COUNT}")
                error_words.append(word)
                continue
            
            # Дополнительная валидация каждого варианта
            try:
                for variant in variants_list:
                    # Проверяем что это строка
                    if not isinstance(variant, str):
                        raise ValueError(f"Вариант должен быть строкой, получено: {type(variant)}")
                    
                    # Проверяем что вариант отличается от оригинала
                    if variant.lower() == word.lower():
                        raise ValueError(f"Вариант '{variant}' совпадает с оригиналом")
                    
                    # Проверяем только русские буквы
                    if not is_russian_word(variant):
                        raise ValueError(f"Вариант '{variant}' содержит не-русские буквы")
                
                # Варианты успешно валидированы
                parsed_variants[word] = variants_list
                logger.debug(f"✅ Варианты для '{word}' валидированы")
            
            except ValueError as e:
                logger.warning(f"⚠️ Ошибка валидации для '{word}': {e}")
                error_words.append(word)
                continue
        
        return parsed_variants, error_words
    
    def _extract_json_from_response(self, text: str) -> str:
        """
        Извлечь JSON из текста ответа (LLM может добавить текст вокруг)
        
        Args:
            text: Текст ответа
            
        Returns:
            JSON строка
        """
        # Ищем первый { и последний }
        start = text.find('{')
        end = text.rfind('}')
        
        if start == -1 or end == -1:
            logger.error(f"❌ Не найдены граница JSON в ответе")
            raise ValueError("JSON not found in response")
        
        json_text = text[start:end+1]
        logger.debug(f"🔍 Извлечен JSON ({len(json_text)} символов)")
        return json_text
    
    # ========================================================================
    # FALLBACK ГЕНЕРАЦИЯ
    # ========================================================================
    
    async def _fallback_generation_for_failed_words(self, failed_words: List[str]):
        """
        Fallback: генерация вариантов для конкретных слов, которые не прошли валидацию
        
        Args:
            failed_words: Список слов, для которых не удалась batch-генерация
        """
        logger.warning(
            f"⚠️ Fallback-генерация для {len(failed_words)} слов: {failed_words[:3]}..."
        )
        
        for word in failed_words:
            try:
                # Пробуем сгенерировать для одного слова
                variants = await self.generate_variants_single(word)
                if variants:
                    logger.info(f"✅ Fallback-генерация успешна для '{word}'")
                else:
                    logger.warning(f"⚠️ Fallback-генерация не дала результата для '{word}'")
                    # Используем алгоритмическую генерацию
                    variants = self._algorithmic_generation(word)
                    if variants:
                        logger.info(f"✅ Алгоритмическая генерация для '{word}'")
            
            except Exception as e:
                logger.error(f"❌ Ошибка fallback для '{word}': {e}")
    
    async def generate_variants_single(self, word: str) -> Optional[List[str]]:
        """
        Fallback: генерация вариантов для одного слова
        
        Args:
            word: Слово для генерации
            
        Returns:
            Список из 3 неправильных вариантов или None
        """
        try:
            logger.info(f"📝 Fallback-генерация для слова '{word}'")
            
            user_prompt = get_variant_generation_single_prompt(word)
            messages = [
                {
                    "role": "system",
                    "content": VARIANT_GENERATION_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            response = await self.client.chat_completion(
                messages=messages,
                model=VARIANT_GENERATION_MODEL,
                temperature=0.7,
                max_tokens=500
            )
            
            # Парсим JSON
            json_text = self._extract_json_from_response(response)
            variants_list = json.loads(json_text)
            
            # Валидируем - проверяем что это список из 3 элементов
            if not isinstance(variants_list, list):
                logger.warning(f"⚠️ Ожидался список, получено: {type(variants_list)}")
                return None
            
            if len(variants_list) != VARIANTS_COUNT:
                logger.warning(f"⚠️ Неверное количество вариантов: {len(variants_list)}, ожидается {VARIANTS_COUNT}")
                return None
            
            # Проверяем каждый вариант
            for variant in variants_list:
                if not isinstance(variant, str):
                    logger.warning(f"⚠️ Вариант должен быть строкой: {type(variant)}")
                    return None
                if variant.lower() == word.lower():
                    logger.warning(f"⚠️ Вариант совпадает с оригиналом: {variant}")
                    return None
                if not is_russian_word(variant):
                    logger.warning(f"⚠️ Вариант содержит не-русские буквы: {variant}")
                    return None
            
            # Сохраняем в кэш
            self._save_variants_to_cache(word, variants_list)
            logger.info(f"✅ Fallback-генерация успешна для '{word}': {variants_list}")
            
            return variants_list
        
        except Exception as e:
            logger.error(f"❌ Ошибка fallback-генерации для '{word}': {e}")
            return None
    
    def _algorithmic_generation(self, word: str) -> Optional[List[str]]:
        """
        Алгоритмическая генерация вариантов (без API)
        
        Улучшенная генерация с 7 стратегиями замены букв
        Гарантирует 3 реалистичных варианта
        
        Args:
            word: Слово для генерации
            
        Returns:
            Список из 3 неправильных вариантов или None
        """
        logger.info(f"🔧 Алгоритмическая генерация для '{word}'")
        
        try:
            word_lower = word.lower()
            variants = set()  # Используем set чтобы избежать дубликатов
            
            # СТРАТЕГИЯ 1: Замена безударной гласной (о→а, е→и, я→е, и→е)
            for old, new in [('о', 'а'), ('а', 'о'), ('е', 'и'), ('и', 'е'), ('я', 'е'), ('ю', 'ю')]:
                idx = word_lower.find(old)
                if idx != -1:
                    variant = word_lower[:idx] + new + word_lower[idx+1:]
                    if variant != word_lower:
                        variants.add(variant)
                        if len(variants) >= VARIANTS_COUNT:
                            break
            
            if len(variants) >= VARIANTS_COUNT:
                result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            
            # СТРАТЕГИЯ 2: Замена парной согласной (д↔т, б↔п, г↔к, в↔ф, ж↔ш, з↔с)
            consonant_pairs = [('д', 'т'), ('т', 'д'), ('б', 'п'), ('п', 'б'), 
                              ('г', 'к'), ('к', 'г'), ('в', 'ф'), ('ф', 'в'), 
                              ('ж', 'ш'), ('ш', 'ж'), ('з', 'с'), ('с', 'з')]
            
            for old, new in consonant_pairs:
                idx = word_lower.find(old)
                if idx != -1:
                    variant = word_lower[:idx] + new + word_lower[idx+1:]
                    if variant != word_lower:
                        variants.add(variant)
                        if len(variants) >= VARIANTS_COUNT:
                            break
            
            if len(variants) >= VARIANTS_COUNT:
                result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            
            # СТРАТЕГИЯ 3: Удвоение согласной (к→кк, р→рр, л→лл, н→нн, м→мм)
            for char in 'крлнмстбпвгджзшщ':
                idx = word_lower.find(char)
                if idx != -1 and idx > 0:
                    # Проверяем что это еще не удвоенная согласная
                    if idx + 1 < len(word_lower) and word_lower[idx + 1] != char:
                        variant = word_lower[:idx+1] + char + word_lower[idx+1:]
                        if variant != word_lower:
                            variants.add(variant)
                            if len(variants) >= VARIANTS_COUNT:
                                break
            
            if len(variants) >= VARIANTS_COUNT:
                result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            
            # СТРАТЕГИЯ 4: Пропуск гласной (убираем гласную)
            for i, char in enumerate(word_lower):
                if char in 'аеиоуюяё':
                    variant = word_lower[:i] + word_lower[i+1:]
                    if variant and variant != word_lower:
                        variants.add(variant)
                        if len(variants) >= VARIANTS_COUNT:
                            break
            
            if len(variants) >= VARIANTS_COUNT:
                result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            
            # СТРАТЕГИЯ 5: Пропуск согласной (убираем согласную)
            for i, char in enumerate(word_lower):
                if char in 'бвгджзклмнпрстфхцчшщ' and i < len(word_lower) - 1:
                    variant = word_lower[:i] + word_lower[i+1:]
                    if variant != word_lower:
                        variants.add(variant)
                        if len(variants) >= VARIANTS_COUNT:
                            break
            
            if len(variants) >= VARIANTS_COUNT:
                result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            
            # СТРАТЕГИЯ 6: Транспозиция (перестановка рядом стоящих букв)
            for i in range(len(word_lower) - 1):
                if word_lower[i] != word_lower[i+1]:
                    variant = word_lower[:i] + word_lower[i+1] + word_lower[i] + word_lower[i+2:]
                    if variant != word_lower:
                        variants.add(variant)
                        if len(variants) >= VARIANTS_COUNT:
                            break
            
            if len(variants) >= VARIANTS_COUNT:
                result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            
            # СТРАТЕГИЯ 7: Добавление гласной
            for i in range(len(word_lower) + 1):
                for vowel in 'аеиоу':
                    variant = word_lower[:i] + vowel + word_lower[i:]
                    if variant != word_lower and len(variant) <= len(word_lower) + 2:
                        variants.add(variant)
                        if len(variants) >= VARIANTS_COUNT:
                            break
                if len(variants) >= VARIANTS_COUNT:
                    break
            
            # Финальная проверка
            result = [v.capitalize() for v in list(variants)[:VARIANTS_COUNT]]
            
            if len(result) >= VARIANTS_COUNT:
                self._save_variants_to_cache(word, result)
                logger.info(f"✅ Алгоритмическая генерация успешна для '{word}': {result}")
                return result
            else:
                logger.warning(f"⚠️ Алгоритмическая генерация дала только {len(result)} вариантов для '{word}'")
                return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка алгоритмической генерации для '{word}': {e}")
            return None
    
    # ========================================================================
    # КЭШИРОВАНИЕ
    # ========================================================================
    
    def _load_cached_variants(self, words_list: List[str]) -> Dict[str, Dict]:
        """
        Загрузить варианты для слов из кэша
        
        Args:
            words_list: Список слов
            
        Returns:
            Словарь {слово: {easy: [...], medium: [...], hard: [...]}}
        """
        cached = {}
        
        for word in words_list:
            variants = self.get_cached_variants(word)
            if variants:
                cached[word] = variants
        
        return cached
    
    def get_cached_variants(self, word: str) -> Optional[List[str]]:
        """
        Получить варианты слова из кэша
        
        Args:
            word: Слово
            
        Returns:
            Список из 3 неправильных вариантов или None
        """
        word_hash = get_word_hash(word)
        cache_file = self.cache_dir / f"{word_hash}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            data = load_json(cache_file)
            if data and "variants" in data:
                logger.debug(f"📖 Варианты '{word}' загружены из кэша")
                return data["variants"]
        
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке кэша для '{word}': {e}")
        
        return None
    
    def get_all_variants(self, word: str) -> Optional[List[str]]:
        """
        Получить все 3 неправильных варианта для слова
        
        Args:
            word: Слово
            
        Returns:
            Список из 3 неправильных вариантов или None
        """
        variants = self.get_cached_variants(word)
        if not variants:
            logger.error(f"❌ Варианты для '{word}' не найдены в кэше")
            return None
        
        logger.debug(f"📖 Загружены 3 варианта для '{word}'")
        return variants
    
    def _save_variants_to_cache(self, word: str, variants_dict: Dict) -> bool:
        """
        Сохранить варианты слова в кэш
        
        Args:
            word: Слово
            variants_dict: Список из 3 неправильных вариантов (новая структура)
            
        Returns:
            True если успешно, False иначе
        """
        try:
            word_hash = get_word_hash(word)
            cache_file = self.cache_dir / f"{word_hash}.json"
            
            from datetime import datetime
            cache_data = {
                "word": word,
                "word_hash": word_hash,
                "generated_at": datetime.now().isoformat(),
                "variants": variants_dict
            }
            
            if save_json(cache_file, cache_data):
                logger.debug(f"💾 Варианты '{word}' сохранены в кэш")
                return True
            else:
                logger.error(f"❌ Ошибка при сохранении кэша для '{word}'")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении в кэш: {e}")
            return False
