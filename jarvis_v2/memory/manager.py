"""
Модуль памяти для J.A.R.V.I.S.
Реализует краткосрочную (контекст) и долгосрочную (векторная БД) память.
"""
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque
import logging
import os

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """Краткосрочная память на основе скользящего окна."""
    
    def __init__(self, max_size: int = 50):
        """
        Args:
            max_size: Максимальное количество элементов в памяти
        """
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        
    def add(self, entry: Dict[str, Any]):
        """Добавляет запись в память."""
        entry['timestamp'] = datetime.now().isoformat()
        self.buffer.append(entry)
        logger.debug(f"Added to STM: {entry.get('type', 'unknown')}")
        
    def get_recent(self, n: int = 10) -> List[Dict]:
        """Получает последние N записей."""
        return list(self.buffer)[-n:]
    
    def clear(self):
        """Очищает память."""
        self.buffer.clear()
        
    def get_context_string(self) -> str:
        """Формирует строку контекста для LLM."""
        if not self.buffer:
            return "No recent context."
        
        context_lines = []
        for entry in self.buffer:
            action = entry.get('action', 'unknown')
            result = entry.get('result', 'no result')
            context_lines.append(f"[{entry['timestamp']}] {action}: {result}")
        
        return "\n".join(context_lines[-20:])  # Последние 20 действий


class LongTermMemory:
    """
    Долгосрочная память с простым векторным поиском.
    В production заменить на FAISS/Chroma/Pinecone.
    """
    
    def __init__(self, storage_path: str = "memory_db.json"):
        self.storage_path = storage_path
        self.entries: List[Dict] = []
        self.load()
        
    def load(self):
        """Загружает память из файла."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.entries = json.load(f)
                logger.info(f"Loaded {len(self.entries)} entries from long-term memory")
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")
                self.entries = []
    
    def save(self):
        """Сохраняет память в файл."""
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
            logger.debug("Long-term memory saved")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
    
    def add_experience(self, situation: str, action: str, outcome: str, 
                       success: bool = True, tags: List[str] = None):
        """
        Добавляет опыт в долгосрочную память.
        
        Args:
            situation: Описание ситуации
            action: Предпринятое действие
            outcome: Результат
            success: Было ли действие успешным
            tags: Теги для категоризации
        """
        entry = {
            'id': hashlib.md5(f"{situation}{action}{datetime.now()}".encode()).hexdigest()[:12],
            'timestamp': datetime.now().isoformat(),
            'situation': situation,
            'action': action,
            'outcome': outcome,
            'success': success,
            'tags': tags or []
        }
        self.entries.append(entry)
        self.save()
        logger.info(f"Added experience to LTM: {action}")
    
    def search_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Ищет похожие ситуации по ключевым словам.
        Примитивный поиск, в будущем заменить на эмбеддинги.
        """
        query_words = set(query.lower().split())
        scored_entries = []
        
        for entry in self.entries:
            text = f"{entry['situation']} {entry['action']} {' '.join(entry['tags'])}".lower()
            score = len(query_words & set(text.split()))
            if score > 0:
                scored_entries.append((score, entry))
        
        scored_entries.sort(reverse=True, key=lambda x: x[0])
        return [entry for _, entry in scored_entries[:limit]]
    
    def get_successful_patterns(self, tag: str = None) -> List[Dict]:
        """Возвращает успешные паттерны действий, опционально фильтруя по тегу."""
        results = [e for e in self.entries if e['success']]
        if tag:
            results = [e for e in results if tag in e.get('tags', [])]
        return results[-10:]  # Последние 10 успешных


class MemoryManager:
    """Управляет обоими типами памяти."""
    
    def __init__(self, stm_size: int = 50, ltm_path: str = "memory_db.json"):
        self.stm = ShortTermMemory(max_size=stm_size)
        self.ltm = LongTermMemory(storage_path=ltm_path)
        
    def record_action(self, action_type: str, details: Dict, result: str, success: bool = True):
        """Записывает действие в оба типа памяти."""
        # В краткосрочную
        self.stm.add({
            'type': 'action',
            'action': action_type,
            'details': details,
            'result': result,
            'success': success
        })
        
        # В долгосрочную (только значимые события)
        if success and action_type in ['click', 'type', 'navigate']:
            situation = details.get('description', 'Unknown situation')
            self.ltm.add_experience(
                situation=situation,
                action=action_type,
                outcome=result,
                success=success,
                tags=[action_type, 'ui_interaction']
            )
    
    def get_full_context(self) -> str:
        """Возвращает полный контекст для LLM."""
        stm_context = self.stm.get_context_string()
        return f"=== Recent Actions ===\n{stm_context}\n\n=== Learned Patterns ===\nCheck long-term memory if needed."
    
    def learn_from_feedback(self, situation: str, action: str, outcome: str, success: bool):
        """Прямое обучение от пользователя или системы."""
        self.ltm.add_experience(situation, action, outcome, success, tags=['feedback'])


# Пример использования
if __name__ == "__main__":
    manager = MemoryManager()
    
    # Симуляция действий
    manager.record_action('click', {'target': 'button_submit'}, 'Clicked submit button', True)
    manager.record_action('type', {'text': 'hello'}, 'Typed text in input field', True)
    
    # Обучение
    manager.learn_from_feedback(
        "User wanted to login",
        "Clicked login button",
        "Successfully logged in",
        True
    )
    
    print(manager.get_full_context())
    print("\nSimilar experiences:", manager.ltm.search_similar("login"))
