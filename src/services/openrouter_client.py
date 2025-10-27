"""
OpenRouter API клиент для работы с Vision, TTS и LLM APIs
"""

import base64
import logging
import asyncio
from typing import Optional, Dict, Any, List
import httpx

from config.settings import OPENROUTER_API_KEY
from config.models import (
    VISION_MODEL,
    OPENROUTER_API_URL,
    OPENROUTER_API_TIMEOUT,
    OPENROUTER_MAX_RETRIES,
)


logger = logging.getLogger(__name__)


class OpenRouterClient:
    """
    Асинхронный HTTP клиент для работы с OpenRouter API
    """
    
    def __init__(self, api_key: str = OPENROUTER_API_KEY):
        """
        Инициализация клиента OpenRouter
        
        Args:
            api_key: API ключ для OpenRouter
        """
        self.api_key = api_key
        self.base_url = OPENROUTER_API_URL
        self.timeout = OPENROUTER_API_TIMEOUT
        self.max_retries = OPENROUTER_MAX_RETRIES
        
        # Проверка API ключа
        if not self.api_key:
            logger.error("❌ OpenRouter API ключ не установлен!")
            raise ValueError("OPENROUTER_API_KEY не найден в переменных окружения")
        
        logger.info(f"✅ OpenRouterClient инициализирован (ключ: {self.api_key[:10]}...)")
    
    async def vision_request(
        self,
        image_base64: str,
        prompt: str,
        model: Optional[str] = None
    ) -> str:
        """
        Отправить запрос для распознавания текста с изображения
        
        Args:
            image_base64: Изображение в формате base64
            prompt: Текстовый промпт для модели
            model: Модель для использования (если не указана, используется VISION_MODEL)
            
        Returns:
            Распознанный текст от модели
            
        Raises:
            Exception: При ошибке API
        """
        if not model:
            model = VISION_MODEL
        
        logger.info(f"📸 Vision запрос: модель {model}")
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1024,
        }
        
        response = await self._make_request(
            endpoint="/chat/completions",
            payload=payload,
            method="POST"
        )
        
        try:
            # Извлечение текста из ответа
            content = response["choices"][0]["message"]["content"]
            logger.info(f"✅ Vision API ответ получен")
            logger.debug(f"📝 Содержимое ответа Vision API:\n{content}")
            return content
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"❌ Ошибка парсинга ответа Vision API: {e}")
            logger.debug(f"Ответ: {response}")
            raise ValueError(f"Невозможно спарсить ответ Vision API: {e}")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        Отправить запрос к LLM для генерации текста
        
        Args:
            messages: Список сообщений в формате OpenAI
            model: Модель для использования
            temperature: Температура генерации (0-1)
            max_tokens: Максимальное количество токенов в ответе
            
        Returns:
            Сгенерированный текст
        """
        logger.info(f"💬 Chat completion запрос: модель {model}")
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        response = await self._make_request(
            endpoint="/chat/completions",
            payload=payload,
            method="POST"
        )
        
        try:
            content = response["choices"][0]["message"]["content"]
            logger.info(f"✅ Chat completion ответ получен")
            return content
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"❌ Ошибка парсинга ответа Chat completion: {e}")
            raise ValueError(f"Невозможно спарсить ответ: {e}")
    
    async def _make_request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        method: str = "POST"
    ) -> Dict[str, Any]:
        """
        Базовый метод для выполнения HTTP запросов к OpenRouter
        
        Args:
            endpoint: Путь к API endpoint (/chat/completions, /audio/speech, etc.)
            payload: Тело запроса
            method: HTTP метод (POST, GET, etc.)
            
        Returns:
            Распарсенный JSON ответ
            
        Raises:
            Exception: При ошибке API или rate limit
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"🔄 Попытка {attempt + 1}/{self.max_retries}: {method} {url}")
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method == "POST":
                        response = await client.post(url, json=payload, headers=headers)
                    elif method == "GET":
                        response = await client.get(url, headers=headers)
                    else:
                        raise ValueError(f"Неподдерживаемый HTTP метод: {method}")
                
                # Проверка статуса ответа
                if response.status_code == 200:
                    logger.debug(f"✅ Успешный ответ (статус 200)")
                    return response.json()
                
                elif response.status_code == 429:  # Rate limit
                    logger.warning(f"⚠️ Rate limit (429). Попытка {attempt + 1}/{self.max_retries}")
                    if attempt < self.max_retries - 1:
                        # Экспоненциальная задержка перед повтором
                        wait_time = (2 ** attempt) * 5  # 5, 10, 20, 40 секунд
                        logger.info(f"⏳ Ожидание {wait_time} сек перед повторением...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(f"Rate limit после {self.max_retries} попыток")
                
                elif response.status_code == 401:
                    logger.error(f"❌ Неавторизованный запрос (401) - проверьте API ключ")
                    raise RuntimeError("API ключ невалиден или отсутствует")
                
                elif response.status_code == 400:
                    error_detail = response.text
                    logger.error(f"❌ Ошибка валидации запроса (400): {error_detail}")
                    raise RuntimeError(f"Ошибка валидации запроса: {error_detail}")
                
                else:
                    logger.error(f"❌ Ошибка API: статус {response.status_code}")
                    logger.error(f"Ответ: {response.text}")
                    raise RuntimeError(f"API ошибка: статус {response.status_code}")
            
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout при попытке {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    raise RuntimeError(f"Timeout после {self.max_retries} попыток")
            
            except httpx.RequestError as e:
                logger.warning(f"❌ Сетевая ошибка при попытке {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    raise RuntimeError(f"Сетевая ошибка после {self.max_retries} попыток: {e}")
        
        raise RuntimeError(f"Запрос не выполнен после {self.max_retries} попыток")
