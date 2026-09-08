"""
Модуль предобработки изображений для улучшения "зрения" J.A.R.V.I.S.
Использует OpenCV для улучшения качества скриншотов перед отправкой в LLM.
"""
import cv2
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """Класс для предобработки изображений экрана."""
    
    def __init__(self, target_width: int = 1920, target_height: int = 1080):
        """
        Инициализация препроцессора.
        
        Args:
            target_width: Целевая ширина изображения
            target_height: Целевая высота изображения
        """
        self.target_size = (target_width, target_height)
        
    def preprocess(self, image: np.ndarray, 
                   enhance_contrast: bool = True,
                   reduce_noise: bool = True,
                   sharpen: bool = False,
                   focus_mode: str = 'full') -> np.ndarray:
        """
        Применяет цепочку улучшений к изображению.
        
        Args:
            image: Исходное изображение (BGR или BGRA)
            enhance_contrast: Улучшить контраст через CLAHE
            reduce_noise: Удалить шум через bilateral filter
            sharpen: Применить резкость
            focus_mode: 'full' - всё изображение, 'center' - центр с контекстом,
                       'cursor' - область вокруг курсора
            
        Returns:
            Обработанное изображение
        """
        # Конвертация в BGR если есть альфа-канал
        if len(image.shape) == 3 and image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        
        # Ресайз к стандартному размеру
        image = cv2.resize(image, self.target_size, interpolation=cv2.INTER_LANCZOS4)
        
        # Удаление шума (сохраняет края лучше чем Gaussian)
        if reduce_noise:
            image = cv2.bilateralFilter(image, 9, 75, 75)
        
        # Улучшение контраста через CLAHE (работает только с одноканальными)
        if enhance_contrast:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
            lab[:, :, 0] = l_channel
            image = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Повышение резкости
        if sharpen:
            kernel = np.array([[-1, -1, -1],
                              [-1,  9, -1],
                              [-1, -1, -1]])
            image = cv2.filter2D(image, -1, kernel)
        
        return image
    
    def extract_region_of_interest(self, image: np.ndarray,
                                   cursor_pos: Optional[Tuple[int, int]] = None,
                                   region_type: str = 'cursor',
                                   context_size: int = 300) -> np.ndarray:
        """
        Выделяет область интереса для детального анализа.
        
        Args:
            image: Полное изображение
            cursor_pos: Позиция курсора (x, y)
            region_type: Тип области ('cursor', 'center', 'custom')
            context_size: Размер области вокруг точки интереса
            
        Returns:
            Вырезанная область интереса
        """
        h, w = image.shape[:2]
        
        if region_type == 'cursor' and cursor_pos:
            x, y = cursor_pos
            x1, y1 = max(0, x - context_size), max(0, y - context_size)
            x2, y2 = min(w, x + context_size), min(h, y + context_size)
            return image[y1:y2, x1:x2]
        
        elif region_type == 'center':
            cx, cy = w // 2, h // 2
            x1, y1 = max(0, cx - context_size), max(0, cy - context_size)
            x2, y2 = min(w, cx + context_size), min(h, cy + context_size)
            return image[y1:y2, x1:x2]
        
        return image
    
    def detect_ui_elements(self, image: np.ndarray) -> list:
        """
        Детектирует простые UI элементы (кнопки, поля ввода) через эвристики.
        Возвращает список bounding boxes.
        
        Note: Это базовая реализация, в будущем можно заменить на ML-модель.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        
        # Поиск контуров
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        ui_elements = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if 1000 < area < 50000:  # Фильтр по размеру
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / float(h)
                
                # Эвристика для кнопок и полей
                if 0.5 < aspect_ratio < 5:
                    ui_elements.append((x, y, w, h))
        
        return ui_elements


# Пример использования
if __name__ == "__main__":
    # Тестовое изображение
    test_image = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    preprocessor = ImagePreprocessor()
    enhanced = preprocessor.preprocess(test_image, enhance_contrast=True, reduce_noise=True)
    
    print(f"Original shape: {test_image.shape}")
    print(f"Enhanced shape: {enhanced.shape}")
    print("Image preprocessing module ready!")
