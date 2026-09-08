"""
Система логгирования и отладки для J.A.R.V.I.S. v2
Включает визуализацию действий, голосовой вывод и детальное логирование.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import json
import asyncio


class ColoredFormatter(logging.Formatter):
    """Цветной форматтер для консольных логов."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(log_dir: str = "logs", 
                  level: int = logging.INFO,
                  console_output: bool = True,
                  file_output: bool = True) -> logging.Logger:
    """
    Настраивает систему логгирования.
    
    Args:
        log_dir: Директория для логов
        level: Уровень логгирования
        console_output: Вывод в консоль
        file_output: Вывод в файл
    """
    logger = logging.getLogger("jarvis")
    logger.setLevel(level)
    logger.handlers.clear()
    
    # Создаём директорию
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Форматы
    detailed_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_format = logging.Formatter(
        '%(levelname)s | %(message)s'
    )
    
    # Консольный обработчик
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter('%(levelname)s | %(message)s'))
        logger.addHandler(console_handler)
    
    # Файловый обработчик (общий)
    if file_output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(
            log_path / f"jarvis_{timestamp}.log", 
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_format)
        logger.addHandler(file_handler)
        
        # Отдельный файл для ошибок
        error_handler = logging.FileHandler(
            log_path / f"errors_{timestamp}.log",
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_format)
        logger.addHandler(error_handler)
    
    logger.info("Logging system initialized")
    return logger


class ActionVisualizer:
    """Визуализирует действия J.A.R.V.I.S. на экране."""
    
    def __init__(self, show_cursor_trail: bool = True, 
                 highlight_clicks: bool = True,
                 overlay_duration: float = 1.0):
        self.show_cursor_trail = show_cursor_trail
        self.highlight_clicks = highlight_clicks
        self.overlay_duration = overlay_duration
        self.cursor_trail: List[tuple] = []
        self.max_trail_length = 20
        
    def mark_click(self, x: int, y: int, button: str = 'left'):
        """Отмечает клик на экране (визуальный эффект)."""
        # В реальной реализации здесь будет отрисовка круга вокруг курсора
        print(f"[VISUAL] Click at ({x}, {y}) with {button} button")
        
    def highlight_region(self, x1: int, y1: int, x2: int, y2: int, 
                        color: str = 'red', label: str = ""):
        """Подсвечивает область на экране."""
        print(f"[VISUAL] Highlight region [{x1}:{x2}, {y1}:{y2}] in {color} - {label}")
        
    def show_cursor_position(self, x: int, y: int):
        """Показывает текущую позицию курсора."""
        if self.show_cursor_trail:
            self.cursor_trail.append((x, y))
            if len(self.cursor_trail) > self.max_trail_length:
                self.cursor_trail.pop(0)
    
    def clear_overlays(self):
        """Очищает все визуальные эффекты."""
        self.cursor_trail.clear()
        print("[VISUAL] Overlays cleared")


class VoiceFeedback:
    """Голосовая обратная связь для действий."""
    
    def __init__(self, enabled: bool = False, rate: int = 150):
        self.enabled = enabled
        self.rate = rate
        self.engine = None
        
        if enabled:
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
                self.engine.setProperty('rate', rate)
            except ImportError:
                print("pyttsx3 not installed. Voice feedback disabled.")
                self.enabled = False
    
    def speak(self, text: str, async_mode: bool = False):
        """Произносит текст."""
        if not self.enabled or not self.engine:
            return
        
        if async_mode:
            asyncio.create_task(self._async_speak(text))
        else:
            self.engine.say(text)
            self.engine.runAndWait()
    
    async def _async_speak(self, text: str):
        """Асинхронная версия речи."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._sync_speak(text))
    
    def _sync_speak(self, text: str):
        self.engine.say(text)
        self.engine.runAndWait()
    
    def announce_action(self, action: str, target: str = ""):
        """Объявляет действие вслух."""
        messages = {
            'click': f"Clicking on {target}",
            'type': f"Typing: {target[:30]}...",
            'scroll': f"Scrolling {target}",
            'open': f"Opening {target}",
            'success': f"Done: {target}",
            'error': f"Error: {target}"
        }
        msg = messages.get(action, f"{action}: {target}")
        self.speak(msg)


class DebugSession:
    """Сессия отладки с записью всех событий."""
    
    def __init__(self, logger: logging.Logger, visualizer: ActionVisualizer,
                 voice: Optional[VoiceFeedback] = None):
        self.logger = logger
        self.visualizer = visualizer
        self.voice = voice
        self.events: List[dict] = []
        self.start_time = datetime.now()
        
    def log_action(self, action_type: str, details: dict, result: str = ""):
        """Логирует действие."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': action_type,
            'details': details,
            'result': result
        }
        self.events.append(event)
        
        # Разные уровни логгирования
        if action_type == 'error':
            self.logger.error(f"{action_type}: {json.dumps(details)}")
        elif action_type in ['warning', 'retry']:
            self.logger.warning(f"{action_type}: {json.dumps(details)}")
        else:
            self.logger.info(f"{action_type}: {json.dumps(details)}")
        
        # Визуализация
        if action_type == 'click' and 'x' in details and 'y' in details:
            self.visualizer.mark_click(details['x'], details['y'])
        
        # Голос
        if self.voice:
            self.voice.announce_action(action_type, result)
    
    def save_recording(self, filepath: str):
        """Сохраняет запись сессии."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'events': self.events
            }, f, indent=2, ensure_ascii=False)
        self.logger.info(f"Session saved to {filepath}")
    
    def get_summary(self) -> dict:
        """Возвращает краткую сводку сессии."""
        return {
            'duration_seconds': (datetime.now() - self.start_time).total_seconds(),
            'total_events': len(self.events),
            'event_types': list(set(e['type'] for e in self.events)),
            'errors': sum(1 for e in self.events if e['type'] == 'error')
        }


# Пример использования
if __name__ == "__main__":
    # Настройка логгирования
    logger = setup_logging(console_output=True, file_output=True)
    
    # Компоненты
    visualizer = ActionVisualizer()
    voice = VoiceFeedback(enabled=False)  # Включить если нужен голос
    session = DebugSession(logger, visualizer, voice)
    
    # Симуляция действий
    session.log_action('click', {'x': 100, 'y': 200, 'button': 'left'}, 'Clicked button')
    session.log_action('type', {'text': 'Hello World'}, 'Typed text')
    session.log_action('navigate', {'url': 'https://example.com'}, 'Navigated')
    
    # Сводка
    summary = session.get_summary()
    logger.info(f"Session summary: {summary}")
    
    # Сохранение
    session.save_recording("debug_session.json")
