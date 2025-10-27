"""
Скрипт для тестирования batch-генерации вариантов через OpenRouter API
Проверяет обращение к API и парсинг ответа
"""

import asyncio
import logging
from pathlib import Path

# Инициализация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Добавляем текущую директорию в path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.services.variant_generator_service import VariantGeneratorService
from src.utils.file_helpers import load_json
import shutil


async def test_api_batch_generation():
    """Тест batch-генерации вариантов через OpenRouter API"""
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТИРОВАНИЕ BATCH-ГЕНЕРАЦИИ ЧЕРЕЗ OpenRouter API")
    logger.info("=" * 80)
    
    # Инициализируем сервис
    service = VariantGeneratorService()
    
    # Проблемные слова, для которых ранее не удалось сгенерировать варианты
    test_words = ["вагон", "вокзал", "вчера"]
    
    logger.info(f"\n📝 Слова для тестирования API: {test_words}")
    logger.info(f"📍 Кэш директория: {service.cache_dir}")
    
    # ШАГИ ТЕСТИРОВАНИЯ:
    logger.info("\n" + "=" * 80)
    logger.info("ШАГ 1: Очистка кэша перед тестом (чтобы изолировать API запрос)")
    logger.info("=" * 80)
    
    # Очищаем кэш только для тестируемых слов
    from src.utils.word_helpers import get_word_hash
    
    cleared_count = 0
    for word in test_words:
        word_hash = get_word_hash(word)
        cache_file = service.cache_dir / f"{word_hash}.json"
        if cache_file.exists():
            cache_file.unlink()
            cleared_count += 1
            logger.info(f"   🗑️  Удален кэш для '{word}'")
    
    if cleared_count == 0:
        logger.info(f"   ℹ️  Кэш для этих слов уже был пуст")
    else:
        logger.info(f"   ✅ Очищено {cleared_count} файлов кэша")
    
    # ШАГ 2: Тест прямого API запроса
    logger.info("\n" + "=" * 80)
    logger.info("ШАГ 2: Прямой тест API запроса (без кэша)")
    logger.info("=" * 80)
    
    logger.info(f"\n🔄 Отправляю batch-запрос для {len(test_words)} слов...")
    logger.info(f"   Слова: {test_words}")
    
    # Вызываем метод batch-генерации
    result = await service.generate_variants_batch(test_words)
    
    # Анализируем результат
    logger.info(f"\n✅ Ответ от API получен:")
    logger.info(f"   Количество слов в ответе: {len(result)}")
    
    for word in test_words:
        if word in result:
            variants = result[word]
            logger.info(f"   {word:15} → {len(variants)} вариантов: {variants}")
        else:
            logger.warning(f"   {word:15} → ❌ ОТСУТСТВУЕТ в ответе")
    
    # ШАГ 3: Проверка качества ответа API
    logger.info("\n" + "=" * 80)
    logger.info("ШАГ 3: ПРОВЕРКА КАЧЕСТВА API ОТВЕТА")
    logger.info("=" * 80)
    
    api_success_count = 0
    api_errors = []
    
    for word in test_words:
        if word not in result:
            api_errors.append(f"{word}: отсутствует в ответе")
            continue
        
        variants = result[word]
        logger.info(f"\n📄 Слово: '{word}'")
        logger.info(f"   Варианты: {variants}")
        
        # Проверяем условия
        checks = {
            "Количество вариантов == 3": len(variants) == 3,
            "Все это строки": all(isinstance(v, str) for v in variants),
            "Все отличаются от оригинала": all(v != word for v in variants),
            "Все не пустые": all(len(v) > 0 for v in variants),
            "Заглавные буквы": all(v[0].isupper() or v[0].isdigit() for v in variants)
        }
        
        all_good = all(checks.values())
        
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            logger.info(f"   {status} {check_name}")
        
        if all_good:
            logger.info(f"   🎉 Качество: ОТЛИЧНО")
            api_success_count += 1
        else:
            logger.warning(f"   ⚠️  Качество: ЕСТЬ ПРОБЛЕМЫ")
            for check_name, passed in checks.items():
                if not passed:
                    api_errors.append(f"{word}: {check_name}")
    
    # ШАГ 4: Проверка что вариант загруженные из кэша
    logger.info("\n" + "=" * 80)
    logger.info("ШАГ 4: ПРОВЕРКА ЧТО ВАРИАНТЫ БЫЛИ СОХРАНЕНЫ В КЭШ")
    logger.info("=" * 80)
    
    cache_verified_count = 0
    for word in test_words:
        if word in result:
            word_hash = get_word_hash(word)
            cache_file = service.cache_dir / f"{word_hash}.json"
            
            if cache_file.exists():
                cached_data = load_json(cache_file)
                if cached_data and "variants" in cached_data:
                    cached_variants = cached_data["variants"]
                    api_variants = result[word]
                    
                    if cached_variants == api_variants:
                        logger.info(f"   ✅ '{word}': варианты сохранены в кэш корректно")
                        cache_verified_count += 1
                    else:
                        logger.warning(f"   ⚠️  '{word}': варианты в кэше отличаются от API")
                        logger.warning(f"      API: {api_variants}")
                        logger.warning(f"      Кэш: {cached_variants}")
                else:
                    logger.warning(f"   ⚠️  '{word}': кэш файл не содержит 'variants'")
            else:
                logger.warning(f"   ⚠️  '{word}': кэш файл не найден после генерации")
    
    # ФИНАЛЬНЫЙ ОТЧЕТ
    logger.info("\n" + "=" * 80)
    logger.info("📋 ФИНАЛЬНЫЙ ОТЧЕТ API ТЕСТИРОВАНИЯ")
    logger.info("=" * 80)
    
    total_words = len(test_words)
    
    logger.info(f"\n📊 РЕЗУЛЬТАТЫ:")
    logger.info(f"   Всего слов: {total_words}")
    logger.info(f"   Получено от API: {len(result)} слов")
    logger.info(f"   Успешные варианты: {api_success_count}/{total_words}")
    logger.info(f"   Сохранено в кэш: {cache_verified_count}/{total_words}")
    
    if api_errors:
        logger.warning(f"\n   ⚠️  Найдено ошибок:")
        for error in api_errors:
            logger.warning(f"      - {error}")
    
    # Финальное решение
    success_rate = (api_success_count / total_words * 100) if total_words > 0 else 0
    
    logger.info(f"\n   📈 Процент успеха: {success_rate:.1f}%")
    
    if success_rate == 100:
        logger.info("   🎉 API РАБОТАЕТ ОТЛИЧНО! ВСЕ СЛОВА ОБРАБОТАНЫ КОРРЕКТНО!")
    elif success_rate >= 80:
        logger.warning(f"   ⚠️  API частично работает ({success_rate:.0f}%)")
    else:
        logger.error(f"   ❌ API имеет проблемы! Успех только {success_rate:.0f}%")
    
    logger.info("=" * 80 + "\n")
    
    return api_success_count == total_words


async def test_single_word_fallback():
    """Тест fallback генерации для одного слова"""
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТИРОВАНИЕ FALLBACK ГЕНЕРАЦИИ (для одного слова)")
    logger.info("=" * 80)
    
    service = VariantGeneratorService()
    
    test_word = "вагон"
    
    logger.info(f"\n📝 Слово для тестирования: '{test_word}'")
    
    # Очищаем кэш
    from src.utils.word_helpers import get_word_hash
    word_hash = get_word_hash(test_word)
    cache_file = service.cache_dir / f"{word_hash}.json"
    if cache_file.exists():
        cache_file.unlink()
        logger.info(f"   🗑️  Очищен кэш для '{test_word}'")
    
    logger.info(f"\n🔄 Отправляю fallback-запрос для одного слова...")
    
    variants = await service.generate_variants_single(test_word)
    
    if variants:
        logger.info(f"✅ Fallback успешен!")
        logger.info(f"   Варианты: {variants}")
        logger.info(f"   Количество: {len(variants)}")
        
        if len(variants) == 3:
            logger.info(f"   🎉 Ровно 3 варианта - ОТЛИЧНО!")
            return True
        else:
            logger.warning(f"   ⚠️  Неверное количество вариантов: {len(variants)} вместо 3")
            return False
    else:
        logger.error(f"❌ Fallback вернул None")
        return False


if __name__ == "__main__":
    async def main():
        # Тест 1: API batch-генерация
        api_success = await test_api_batch_generation()
        
        # Тест 2: Fallback для одного слова
        logger.info("\n")
        fallback_success = await test_single_word_fallback()
        
        # Итоговый результат
        logger.info("\n" + "=" * 80)
        logger.info("🏁 ИТОГОВЫЙ РЕЗУЛЬТАТ ВСЕХ ТЕСТОВ")
        logger.info("=" * 80)
        
        if api_success and fallback_success:
            logger.info("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        else:
            logger.warning("⚠️  Некоторые тесты провалились")
            if not api_success:
                logger.warning("   - API batch-генерация имеет проблемы")
            if not fallback_success:
                logger.warning("   - Fallback генерация имеет проблемы")
        
        logger.info("=" * 80 + "\n")
    
    asyncio.run(main())
