"""
Асинхронное ядро J.A.R.V.I.S. v2
Реализует неблокирующую архитектуру с очередями задач.
"""
import asyncio
import aiohttp
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str
    name: str
    coroutine: Callable
    args: tuple
    kwargs: dict
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def __post_init__(self):
        self.created_at = time.time()


class AsyncTaskManager:
    """Менеджер асинхронных задач с приоритетами."""
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.results: Dict[str, Any] = {}
        self._shutdown = False
        
    async def submit(self, task: Task, priority: int = 10) -> str:
        """Добавляет задачу в очередь."""
        await self.task_queue.put((priority, task.id, task))
        logger.info(f"Task {task.id} submitted with priority {priority}")
        return task.id
    
    async def _worker(self, worker_id: int):
        """Воркер для обработки задач из очереди."""
        while not self._shutdown:
            try:
                priority, task_id, task = await asyncio.wait_for(
                    self.task_queue.get(), 
                    timeout=1.0
                )
                
                async with self.semaphore:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
                    self.running_tasks[task.id] = asyncio.current_task()
                    
                    try:
                        if asyncio.iscoroutinefunction(task.coroutine):
                            result = await task.coroutine(*task.args, **task.kwargs)
                        else:
                            # Запуск синхронной функции в executor
                            loop = asyncio.get_event_loop()
                            result = await loop.run_in_executor(
                                None, 
                                lambda: task.coroutine(*task.args, **task.kwargs)
                            )
                        
                        task.status = TaskStatus.COMPLETED
                        task.result = result
                        self.results[task.id] = result
                        
                    except Exception as e:
                        task.status = TaskStatus.FAILED
                        task.error = e
                        logger.error(f"Task {task.id} failed: {e}")
                    
                    finally:
                        task.completed_at = time.time()
                        self.running_tasks.pop(task.id, None)
                        self.task_queue.task_done()
                        
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
    
    async def start_workers(self, num_workers: int = 3):
        """Запускает воркеров."""
        workers = [asyncio.create_task(self._worker(i)) for i in range(num_workers)]
        return workers
    
    async def get_result(self, task_id: str, timeout: float = 30.0) -> Any:
        """Ждёт результат задачи."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if task_id in self.results:
                result = self.results.pop(task_id)
                return result
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Task {task_id} did not complete in {timeout}s")
    
    async def shutdown(self):
        """Останавливает все задачи."""
        self._shutdown = True
        for task in self.running_tasks.values():
            task.cancel()


class AsyncVisionService:
    """Асинхронный сервис для работы с изображением."""
    
    def __init__(self, preprocessor, api_key: str, api_url: str):
        self.preprocessor = preprocessor
        self.api_key = api_key
        self.api_url = api_url
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def analyze_screen(self, screenshot: bytes, prompt: str) -> Dict:
        """Анализирует скриншот через LLM API."""
        if not self.session:
            raise RuntimeError("Session not initialized")
        
        # Предобработка в отдельном потоке
        loop = asyncio.get_event_loop()
        # Здесь должна быть логика обработки изображения
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": "vision-model",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        }
        
        async with self.session.post(self.api_url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                raise Exception(f"API error: {resp.status}")


class EventSystem:
    """Система событий для слабой связности компонентов."""
    
    def __init__(self):
        self.subscribers: Dict[str, list] = {}
        
    def subscribe(self, event_type: str, callback: Callable):
        """Подписывается на событие."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type}")
    
    def publish(self, event_type: str, data: Any = None):
        """Публикует событие."""
        callbacks = self.subscribers.get(event_type, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(data))
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Event handler error for {event_type}: {e}")


# Пример использования
async def main():
    manager = AsyncTaskManager(max_concurrent=3)
    workers = await manager.start_workers(num_workers=2)
    
    async def sample_task(x: int, y: int) -> int:
        await asyncio.sleep(1)
        return x + y
    
    # Добавление задач
    task1 = Task("task1", "add", sample_task, (5, 3), {})
    task2 = Task("task2", "add", sample_task, (10, 20), {})
    
    await manager.submit(task1, priority=5)
    await manager.submit(task2, priority=1)
    
    # Получение результатов
    result1 = await manager.get_result("task1")
    result2 = await manager.get_result("task2")
    
    print(f"Results: {result1}, {result2}")
    
    await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
