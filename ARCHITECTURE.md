# 🏗️ Архитектура проекта

## Общая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                  TELEGRAM CLIENT                             │
│         (Пользователь в мобильном приложении)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ (Telegram Bot API)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│             AIOGRAM BOT (Python async)                       │
│  Главный диспетчер событий и маршрутизация                  │
│                                                              │
│  main.py                                                    │
│   ├─ setup_logging()          - логирование                │
│   ├─ init_directories()       - инициализация папок        │
│   ├─ set_default_commands()   - меню команд                │
│   └─ main() - polling loop                                 │
└──────────────┬─────────────────────────┬────────────────────┘
               │                         │
               ▼                         ▼
    ┌──────────────────┐      ┌──────────────────┐
    │  HANDLERS        │      │  ROUTERS         │
    │  (event handlers)│      │  (маршрутизация) │
    └──────────────────┘      └──────────────────┘
               │
               ├─ start_handler.py
               │   ├─ cmd_start()   - /start
               │   ├─ cmd_help()    - /help
               │   ├─ cmd_menu()    - /menu
               │   └─ handle_unknown()
               │
               ├─ photo_handler.py (Этап 1)
               │   └─ handle_photo() - загрузка фото
               │
               ├─ learning_handler.py (Этап 5)
               │   └─ Обучение словам
               │
               └─ progress_handler.py (Этап 7)
                   └─ Статистика
```

## Архитектура с сервисами (после Этапа 2)

```
┌────────────────────────────────────────────────────────────┐
│                   HANDLERS (Telegram UI)                    │
│  Получают события и вызывают нужные сервисы/бизнес-логику │
└────────────┬──────────────────────────────┬────────────────┘
             │                              │
             ▼                              ▼
   ┌──────────────────┐        ┌──────────────────────┐
   │   KEYBOARDS      │        │  STATES (FSM)        │
   │  (UI клавиатуры) │        │ (Finite State Mach.) │
   └──────────────────┘        └──────────────────────┘


┌────────────────────────────────────────────────────────────┐
│                  SERVICES LAYER                             │
│  Работа с внешними API (OpenRouter, Telegram)             │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  openrouter_client.py                                      │
│   ├─ vision_request()        - распознавание текста        │
│   ├─ tts_request()           - озвучивание слов            │
│   ├─ chat_completion()       - LLM запросы                 │
│   └─ _make_request()         - базовый HTTP клиент        │
│                                                             │
│  vision_service.py                                         │
│   ├─ recognize_text()        - распознавание фото          │
│   ├─ parse_response()        - парсинг результата          │
│   └─ _prepare_image()        - предобработка               │
│                                                             │
│  tts_service.py                                            │
│   ├─ generate_audio()        - генерация аудио             │
│   ├─ get_cached_audio()      - из кэша                     │
│   └─ save_to_cache()         - сохранение в кэш            │
│                                                             │
│  variant_generator_service.py                              │
│   ├─ generate_variants_batch()  - batch-генерация          │
│   ├─ generate_variants_single() - fallback                 │
│   ├─ get_cached_variants()      - из кэша                  │
│   ├─ save_to_cache()            - сохранение               │
│   └─ select_variants_by_difficulty() - выбор по сложности  │
│                                                             │
└────────────────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────┐
│              CORE BUSINESS LOGIC LAYER                      │
│  Основная бизнес-логика приложения                        │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  dictionary_manager.py                                     │
│   ├─ create_dictionary()      - создание словаря           │
│   ├─ get_dictionary()         - получение словаря          │
│   ├─ update_dictionary()      - обновление                 │
│   ├─ delete_dictionary()      - удаление                   │
│   └─ list_dictionaries()      - список                     │
│                                                             │
│  learning_session.py                                       │
│   ├─ initialize()             - инициализация сессии       │
│   ├─ get_next_word()          - следующее слово            │
│   ├─ generate_variants()      - варианты ответов           │
│   ├─ record_answer()          - запись результата          │
│   └─ finish_session()         - завершение                 │
│                                                             │
│  adaptive_learning.py                                      │
│   ├─ update_word_status()     - обновление статуса         │
│   ├─ get_next_word_priority() - приоритет слова            │
│   ├─ is_word_mastered()       - выучено ли на "5"?         │
│   └─ is_session_complete()    - все слова выучены?         │
│                                                             │
│  progress_tracker.py                                       │
│   ├─ update_word_progress()   - обновление                 │
│   ├─ get_word_status()        - статус слова               │
│   ├─ get_dictionary_progress() - по словарю                │
│   └─ get_total_progress()     - общий прогресс             │
│                                                             │
└────────────────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────┐
│                UTILS / HELPERS LAYER                        │
│  Вспомогательные функции и валидация                       │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  image_processor.py                                        │
│   ├─ preprocess_image()       - улучшение контраста        │
│   ├─ convert_to_base64()      - для API                    │
│   └─ validate_image()         - проверка формата           │
│                                                             │
│  word_helpers.py                                           │
│   ├─ shuffle_variants()       - перемешивание              │
│   ├─ get_word_hash()          - хеш для кэша               │
│   └─ format_variants_for_keyboard() - форматирование       │
│                                                             │
│  file_helpers.py                                           │
│   ├─ ensure_user_directories() - папки пользователя       │
│   ├─ save_json()              - сохранение JSON            │
│   ├─ load_json()              - загрузка JSON              │
│   └─ generate_unique_id()     - уникальный ID              │
│                                                             │
│  validators.py                                             │
│   ├─ validate_words_list()    - валидация списка           │
│   ├─ sanitize_word()          - очистка слова              │
│   └─ Pydantic models          - схемы валидации            │
│                                                             │
└────────────────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────┐
│                  DATA STORAGE LAYER                         │
│  Файловая система (JSON, кэши)                            │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  data/                                                     │
│  ├─ users/{user_id}/                                       │
│  │  ├─ dictionaries/{dict_id}.json                         │
│  │  ├─ progress.json                                       │
│  │  └─ sessions/{session_id}.json                          │
│  ├─ audio_cache/{word_hash}.mp3                            │
│  └─ variants_cache/{word_hash}.json                        │
│                                                             │
│  logs/                                                     │
│  └─ bot.log                                                │
│                                                             │
└────────────────────────────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────────────────────────────┐
│              EXTERNAL APIs (OpenRouter)                     │
│  Сторонние сервисы                                         │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Vision API (Распознавание текста)                         │
│  ├─ google/gemini-pro-vision                              │
│  └─ openai/gpt-4o                                          │
│                                                             │
│  TTS API (Озвучивание)                                     │
│  └─ openai/tts-1                                           │
│                                                             │
│  LLM API (Генерация вариантов)                             │
│  ├─ anthropic/claude-3-haiku (основная)                   │
│  └─ openai/gpt-3.5-turbo (fallback)                        │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

## Поток данных: От фото до обучения

```
1. ЗАГРУЗКА ФОТО
   ┌──────────────────────┐
   │ Пользователь        │
   │ отправляет фото      │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────────────────┐
   │ photo_handler.py                 │
   │ handle_photo()                   │
   └──────────┬───────────────────────┘
              │
              ▼ (фото файл)
   ┌──────────────────────────────────┐
   │ image_processor.py               │
   │ preprocess_image() + validate()  │
   └──────────┬───────────────────────┘
              │
              ▼ (base64 изображение)

2. РАСПОЗНАВАНИЕ ТЕКСТА
   ┌──────────────────────────────────┐
   │ vision_service.py                │
   │ recognize_text()                 │
   └──────────┬───────────────────────┘
              │
              ▼ (промпт из config/prompts.py)
   ┌──────────────────────────────────┐
   │ openrouter_client.py             │
   │ vision_request()                 │
   │ → API Google Gemini/OpenAI       │
   └──────────┬───────────────────────┘
              │
              ▼ (список слов)
   ┌──────────────────────────────────┐
   │ validators.py                    │
   │ validate_words_list()            │
   └──────────┬───────────────────────┘
              │
              ▼ (очищенный список)

3. BATCH-ГЕНЕРАЦИЯ ВАРИАНТОВ
   ┌──────────────────────────────────┐
   │ dictionary_manager.py            │
   │ create_dictionary()              │
   └──────────┬───────────────────────┘
              │
              ▼ (все слова одним запросом)
   ┌──────────────────────────────────┐
   │ variant_generator_service.py     │
   │ generate_variants_batch()        │
   └──────────┬───────────────────────┘
              │
              ▼ (batch-промпт)
   ┌──────────────────────────────────┐
   │ openrouter_client.py             │
   │ chat_completion()                │
   │ → API Claude 3 Haiku             │
   └──────────┬───────────────────────┘
              │
              ▼ (JSON с вариантами для каждого слова)
   ┌──────────────────────────────────┐
   │ file_helpers.py                  │
   │ save_json()                      │
   │ → data/variants_cache/           │
   └──────────┬───────────────────────┘
              │
              ▼

4. НАЧАЛО ОБУЧЕНИЯ
   ┌──────────────────────────────────┐
   │ learning_handler.py              │
   │ start_learning_session()         │
   └──────────┬───────────────────────┘
              │
              ▼
   ┌──────────────────────────────────┐
   │ learning_session.py              │
   │ initialize()                     │
   └──────────┬───────────────────────┘
              │
              ├─ Получить слово (adaptive_learning)
              ├─ Сгенерировать аудио (tts_service)
              ├─ Выбрать варианты (variant_generator)
              └─ Показать пользователю
              │
              ▼
   ┌──────────────────────────────────┐
   │ Пользователь выбирает ответ      │
   └──────────┬───────────────────────┘
              │
              ▼
   ┌──────────────────────────────────┐
   │ adaptive_learning.py             │
   │ update_word_status()             │
   │ is_word_mastered()               │
   │ get_next_word_priority()         │
   └──────────┬───────────────────────┘
              │
              ▼ (обновить статистику)
   ┌──────────────────────────────────┐
   │ progress_tracker.py              │
   │ update_word_progress()           │
   └──────────┬───────────────────────┘
              │
              ▼ (все слова выучены на "5"?)
              ├─ НЕТ → вернуться на шаг "Получить слово"
              └─ ДА → завершение сессии
                      └─ Торжественное сообщение
                      └─ Сохранить статистику
                      └─ Вернуться в меню
```

## Конфигурационные слои

```
┌─────────────────────────────────────────┐
│         CONFIG LAYER (Ценральная конфигурация)  │
├─────────────────────────────────────────┤
│                                         │
│  settings.py                            │
│  ├─ API токены и ключи                  │
│  ├─ Пути к папкам (DATA_DIR, etc.)      │
│  ├─ Параметры обучения                  │
│  │  └─ MASTERY_CONSECUTIVE_CORRECT = 3  │
│  ├─ Параметры генерации                 │
│  │  └─ VARIANTS_EASY = 4                │
│  └─ Логирование                         │
│                                         │
│  models.py                              │
│  ├─ VISION_MODEL                        │
│  ├─ VARIANT_GENERATION_MODEL            │
│  ├─ FALLBACK_MODEL                      │
│  ├─ TTS_MODEL_CONFIG                    │
│  ├─ Температура и параметры             │
│  └─ URL OpenRouter API                  │
│                                         │
│  prompts.py                             │
│  ├─ VISION_PROMPT                       │
│  ├─ VARIANT_GENERATION_SYSTEM_PROMPT    │
│  ├─ VARIANT_GENERATION_BATCH_PROMPT     │
│  ├─ VARIANT_GENERATION_SINGLE_PROMPT    │
│  └─ Функции подстановки переменных      │
│                                         │
└─────────────────────────────────────────┘
```

## Модели данных

```
┌─────────────────────────────────────────┐
│  MODELS (src/core/models.py)            │
├─────────────────────────────────────────┤
│                                         │
│  Word                                   │
│  ├─ text: str                           │
│  ├─ consecutive_correct: int            │
│  ├─ total_attempts: int                 │
│  ├─ correct_count: int                  │
│  ├─ incorrect_count: int                │
│  ├─ is_mastered: bool                   │
│  └─ priority_score: int                 │
│                                         │
│  Dictionary                             │
│  ├─ id: str                             │
│  ├─ created_at: datetime                │
│  ├─ name: str                           │
│  ├─ words: List[Word]                   │
│  └─ is_fully_learned: bool              │
│                                         │
│  UserProgress                           │
│  ├─ user_id: int                        │
│  ├─ dictionaries_progress: dict         │
│  ├─ total_words_learned: int            │
│  └─ total_sessions: int                 │
│                                         │
│  SessionStats                           │
│  ├─ session_id: str                     │
│  ├─ started_at: datetime                │
│  ├─ ended_at: datetime                  │
│  ├─ total_words: int                    │
│  ├─ correct_answers: int                │
│  ├─ incorrect_answers: int              │
│  └─ words_mastered: int                 │
│                                         │
└─────────────────────────────────────────┘
```

---

**Архитектура разработана для масштабируемости, модульности и простоты тестирования на каждом этапе разработки.**
