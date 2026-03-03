"""
OCR处理器模块
"""

import os
import time
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
from rapidocr_onnxruntime import RapidOCR
import cv2

from shared.exceptions import OCRProcessingException
from shared.utils import logger, bytes_to_image, time_it
from shared.cache import cached, get_cache


class OCRProcessor:
    """OCR处理器"""

    def __init__(self, model_path: Optional[str] = None):
        """
        初始化OCR处理器

        Args:
            model_path: 模型路径，如果为None则使用默认路径
        """
        self.model_path = model_path
        self.ocr = None
        self.initialized = False
        self.init_time = None
        self._initialize()

    def _initialize(self):
        """初始化OCR模型"""
        try:
            start_time = time.time()
            logger.info("ocr_processor_initializing", model_path=self.model_path)

            # 初始化RapidOCR
            # 如果提供了模型路径，使用自定义路径
            if self.model_path and os.path.exists(self.model_path):
                self.ocr = RapidOCR(det_model_path=os.path.join(self.model_path, "det.onnx"),
                                   rec_model_path=os.path.join(self.model_path, "rec.onnx"),
                                   cls_model_path=os.path.join(self.model_path, "cls.onnx"))
            else:
                # 使用默认模型（会自动下载）
                self.ocr = RapidOCR()

            self.initialized = True
            self.init_time = time.time() - start_time

            logger.info("ocr_processor_initialized",
                        initialization_time=self.init_time,
                        model_loaded=True)

        except Exception as e:
            logger.error("ocr_processor_init_failed", error=str(e))
            raise OCRProcessingException(f"Failed to initialize OCR processor: {str(e)}")

    def is_ready(self) -> bool:
        """检查OCR处理器是否已准备好"""
        return self.initialized and self.ocr is not None

    @cached(namespace="ocr", ttl=86400, key_params=["image_bytes"])  # 24小时缓存
    def scan_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        扫描图像中的文字

        Args:
            image_bytes: 图像字节数据

        Returns:
            识别结果列表，每个结果包含文字、置信度和坐标

        Raises:
            OCRProcessingException: OCR处理失败时抛出
        """
        if not self.is_ready():
            raise OCRProcessingException("OCR processor is not initialized")

        try:
            # 将字节转换为图像
            img = bytes_to_image(image_bytes)
            if img is None:
                raise OCRProcessingException("Failed to decode image")

            # 执行OCR识别
            result, elapse = self.ocr(img)

            if not result:
                return []

            # 格式化结果
            formatted_results = []
            for item in result:
                # item结构: [坐标, 文字, 置信度]
                if len(item) >= 3:
                    coordinates = item[0]
                    text = item[1]
                    confidence = float(item[2]) if len(item) > 2 else 0.0

                    formatted_results.append({
                        "text": text,
                        "confidence": confidence,
                        "coordinates": coordinates,
                        "bounding_box": self._calculate_bounding_box(coordinates)
                    })

            logger.debug("ocr_scan_completed",
                        text_count=len(formatted_results),
                        processing_time=elapse)

            return formatted_results

        except Exception as e:
            logger.error("ocr_scan_error", error=str(e))
            raise OCRProcessingException(f"OCR processing error: {str(e)}")

    def scan_image_with_preprocessing(self, image_bytes: bytes, **preprocess_options) -> List[Dict[str, Any]]:
        """
        带预处理的OCR扫描

        Args:
            image_bytes: 图像字节数据
            **preprocess_options: 预处理选项，例如:
                - resize_to: 调整大小 (width, height)
                - convert_to_grayscale: 是否转换为灰度图
                - enhance_contrast: 是否增强对比度

        Returns:
            识别结果列表
        """
        if not self.is_ready():
            raise OCRProcessingException("OCR processor is not initialized")

        try:
            # 将字节转换为图像
            img = bytes_to_image(image_bytes)
            if img is None:
                raise OCRProcessingException("Failed to decode image")

            # 应用预处理
            img_processed = self._preprocess_image(img, **preprocess_options)

            # 执行OCR识别
            result, elapse = self.ocr(img_processed)

            if not result:
                return []

            # 格式化结果
            formatted_results = []
            for item in result:
                if len(item) >= 3:
                    coordinates = item[0]
                    text = item[1]
                    confidence = float(item[2]) if len(item) > 2 else 0.0

                    # 如果需要，将坐标转换回原始图像空间
                    if "resize_to" in preprocess_options:
                        original_size = (img.shape[1], img.shape[0])  # (width, height)
                        target_size = preprocess_options["resize_to"]
                        coordinates = self._scale_coordinates(coordinates, original_size, target_size)

                    formatted_results.append({
                        "text": text,
                        "confidence": confidence,
                        "coordinates": coordinates,
                        "bounding_box": self._calculate_bounding_box(coordinates),
                        "preprocessing_applied": list(preprocess_options.keys())
                    })

            logger.debug("ocr_scan_with_preprocessing_completed",
                        text_count=len(formatted_results),
                        processing_time=elapse,
                        preprocessing=preprocess_options)

            return formatted_results

        except Exception as e:
            logger.error("ocr_scan_with_preprocessing_error", error=str(e))
            raise OCRProcessingException(f"OCR processing with preprocessing error: {str(e)}")

    def _preprocess_image(self, img: np.ndarray, **options) -> np.ndarray:
        """
        图像预处理

        Args:
            img: 输入图像
            **options: 预处理选项

        Returns:
            预处理后的图像
        """
        processed = img.copy()

        # 调整大小
        if "resize_to" in options:
            width, height = options["resize_to"]
            processed = cv2.resize(processed, (width, height))

        # 转换为灰度图
        if options.get("convert_to_grayscale", False):
            if len(processed.shape) == 3:
                processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
                # 转换回3通道（某些模型需要）
                processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)

        # 增强对比度
        if options.get("enhance_contrast", False):
            # 使用CLAHE进行对比度限制的自适应直方图均衡化
            lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            processed = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # 降噪
        if options.get("denoise", False):
            processed = cv2.fastNlMeansDenoisingColored(processed, None, 10, 10, 7, 21)

        return processed

    def _calculate_bounding_box(self, coordinates: List[List[float]]) -> Dict[str, float]:
        """
        计算包围盒

        Args:
            coordinates: 多边形坐标 [[x1, y1], [x2, y2], ...]

        Returns:
            包围盒信息 {x, y, width, height}
        """
        if not coordinates:
            return {"x": 0, "y": 0, "width": 0, "height": 0}

        xs = [point[0] for point in coordinates]
        ys = [point[1] for point in coordinates]

        x_min = min(xs)
        x_max = max(xs)
        y_min = min(ys)
        y_max = max(ys)

        return {
            "x": float(x_min),
            "y": float(y_min),
            "width": float(x_max - x_min),
            "height": float(y_max - y_min)
        }

    def _scale_coordinates(self, coordinates: List[List[float]],
                          original_size: Tuple[int, int],
                          target_size: Tuple[int, int]) -> List[List[float]]:
        """
        缩放坐标到原始图像空间

        Args:
            coordinates: 缩放后的坐标
            original_size: 原始图像尺寸 (width, height)
            target_size: 目标图像尺寸 (width, height)

        Returns:
            缩放回原始空间的坐标
        """
        if not coordinates:
            return coordinates

        scale_x = original_size[0] / target_size[0]
        scale_y = original_size[1] / target_size[1]

        scaled_coordinates = []
        for point in coordinates:
            if len(point) >= 2:
                scaled_coordinates.append([
                    point[0] * scale_x,
                    point[1] * scale_y
                ])
            else:
                scaled_coordinates.append(point)

        return scaled_coordinates

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "processor_type": "RapidOCR",
            "initialized": self.initialized,
            "initialization_time": self.init_time,
            "model_path": self.model_path,
            "ready": self.is_ready()
        }


# 全局OCR处理器实例（用于测试）
_global_ocr_processor = None


def get_global_ocr_processor() -> OCRProcessor:
    """获取全局OCR处理器实例"""
    global _global_ocr_processor
    if _global_ocr_processor is None:
        _global_ocr_processor = OCRProcessor()
    return _global_ocr_processor