# J.A.R.V.I.S. v2 - Улучшенная версия

Модульная асинхронная архитектура с улучшенным зрением, памятью и отладкой.

## 🚀 Ключевые улучшения

### 1. **Улучшенное зрение** (`vision/preprocessor.py`)
- Предобработка изображений через OpenCV (CLAHE, шумоподавление, резкость)
- Выделение областей интереса (ROI)
- Детекция UI элементов через эвристики
- Поддержка разных режимов фокуса (полный экран, центр, курсор)

### 2. **Память** (`memory/manager.py`)
- **Краткосрочная память**: скользящее окно последних действий
- **Долгосрочная память**: сохранение успешных паттернов в JSON
- Поиск похожих ситуаций для обучения
- Контекст для LLM из истории действий

### 3. **Асинхронное ядро** (`core/async_engine.py`)
- Очередь задач с приоритетами
- Параллельное выполнение через воркеров
- Event-driven архитектура
- Асинхронный Vision сервис

### 4. **Отладка и визуализация** (`utils/debug_tools.py`)
- Цветное логгирование с разделением по уровням
- Визуализация кликов и выделения областей
- Голосовая обратная связь (опционально)
- Запись сессий в JSON для анализа

## 📁 Структура проекта

```
jarvis_v2/
├── core/
│   └── async_engine.py      # Асинхронное ядро
├── vision/
│   └── preprocessor.py      # Обработка изображений
├── memory/
│   └── manager.py           # Система памяти
├── utils/
│   └── debug_tools.py       # Логгирование и отладка
├── logs/                    # Автоматически создаётся
├── requirements.txt         # Зависимости
└── README.md               # Этот файл
```

## 🔧 Установка

```bash
cd jarvis_v2
pip install -r requirements.txt
```

### Опциональные зависимости
```bash
# Для production векторного поиска
pip install faiss-cpu chromadb

# Для голосовой обратной связи
pip install pyttsx3
```

## 🧪 Тестирование модулей

```bash
# Проверка preprocessora
python vision/preprocessor.py

# Проверка памяти
python memory/manager.py

# Проверка async ядра
python core/async_engine.py

# Проверка инструментов отладки
python utils/debug_tools.py
```

## 📖 Пример использования

```python
from vision.preprocessor import ImagePreprocessor
from memory.manager import MemoryManager
from core.async_engine import AsyncTaskManager, Task
from utils.debug_tools import setup_logging, DebugSession, ActionVisualizer

# Настройка
logger = setup_logging()
preprocessor = ImagePreprocessor()
memory = MemoryManager()
visualizer = ActionVisualizer()
session = DebugSession(logger, visualizer)

# Предобработка скриншота
import numpy as np
screenshot = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
enhanced = preprocessor.preprocess(screenshot, enhance_contrast=True)

# Запись действия
session.log_action('click', {'x': 500, 'y': 300}, 'Clicked button')
memory.record_action('click', {'target': 'button'}, 'Success', True)

# Асинхронная задача
async def my_task():
    return "result"

task = Task("t1", "test", my_task, (), {})
# ... добавить в AsyncTaskManager
```

## 🎯 Следующие шаги

1. **Интеграция модулей** - собрать главный класс J.A.R.V.I.S.
2. **Конфигурация** - добавить YAML/.env конфиги
3. **ML модель** - заменить эвристики детекции на YOLO/DETR
4. **Векторная БД** - подключить FAISS для памяти
5. **Тесты** - покрыть unit и integration тестами

## ⚠️ Заметки

- Это каркас v2, требующий интеграции с основным кодом
- Некоторые функции (голос, визуализация) требуют дополнительных библиотек
- Для production рекомендуется добавить rate limiting и кэширование API запросов
