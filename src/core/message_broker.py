from redis import Redis
from rq import Queue
import aioredis
import json
import logging
from typing import Dict, Any, Optional

class MessageBroker:
    def __init__(self):
        try:
            # Основная очередь для анализа сообщений
            self.redis = Redis(host='localhost', port=6379, db=0)
            self.analysis_queue = Queue('analysis', connection=self.redis)
            
            # Очередь для срочных сообщений (VIP пользователи)
            self.priority_queue = Queue('priority', connection=self.redis)
            
            # Очередь для модерации
            self.moderation_queue = Queue('moderation', connection=self.redis)
            
            # Асинхронное подключение для кэширования
            self.aioredis = aioredis.from_url('redis://localhost')
            
            logging.info("Successfully connected to Redis")
        except Exception as e:
            logging.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def push_message(self, message: Dict[str, Any], priority: bool = False) -> Optional[str]:
        """Отправка сообщения в очередь"""
        try:
            queue = self.priority_queue if priority else self.analysis_queue
            job = queue.enqueue(
                'workers.analyze_message',
                message,
                timeout=300,  # 5 минут таймаут
                result_ttl=3600  # Хранить результат 1 час
            )
            return job.id
        except Exception as e:
            logging.error(f"Failed to push message to queue: {e}")
            return None
    
    async def get_result(self, job_id: str) -> Optional[Dict]:
        """Получение результата обработки"""
        try:
            job = self.analysis_queue.fetch_job(job_id)
            if job is None:
                job = self.priority_queue.fetch_job(job_id)
            
            if job and job.is_finished:
                return job.result
            return None
        except Exception as e:
            logging.error(f"Failed to get job result: {e}")
            return None
    
    async def cache_set(self, key: str, value: Any, expire: int = 3600):
        """Сохранение в кэш"""
        try:
            await self.aioredis.set(key, json.dumps(value), ex=expire)
        except Exception as e:
            logging.error(f"Failed to set cache: {e}")
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Получение из кэша"""
        try:
            value = await self.aioredis.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logging.error(f"Failed to get from cache: {e}")
            return None
    
    async def close(self):
        """Закрытие соединений"""
        try:
            await self.aioredis.close()
            self.redis.close()
        except Exception as e:
            logging.error(f"Failed to close Redis connections: {e}") 