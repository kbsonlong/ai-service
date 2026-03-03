"""
共享工具函数
"""

import os
import time
import uuid
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

import numpy as np
from fastapi import UploadFile, HTTPException


def setup_logging(service_name: str, log_level: str = "INFO", log_format: str = "json") -> logging.Logger:
    """
    设置结构化日志

    Args:
        service_name: 服务名称
        log_level: 日志级别
        log_format: 日志格式（json 或 text）

    Returns:
        配置好的logger实例
    """
    import structlog

    # 配置structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if log_format == "json" else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 设置Python标准库日志级别
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
    )

    return structlog.get_logger(service_name)


def validate_upload_file(
    file: UploadFile,
    allowed_content_types: List[str],
    max_size_bytes: int
) -> Tuple[bytes, str]:
    """
    验证上传文件

    Args:
        file: 上传的文件
        allowed_content_types: 允许的内容类型列表
        max_size_bytes: 最大文件大小（字节）

    Returns:
        tuple: (文件内容bytes, 文件扩展名)

    Raises:
        HTTPException: 如果文件无效
    """
    # 检查文件类型
    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_content_types)}"
        )

    # 读取文件内容
    content = file.file.read()

    # 检查文件大小
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {max_size_bytes // (1024*1024)}MB"
        )

    # 获取文件扩展名
    filename = file.filename or "unknown"
    file_ext = os.path.splitext(filename)[1].lower() or f".{file.content_type.split('/')[-1]}"

    return content, file_ext


def generate_request_id() -> str:
    """生成请求ID"""
    return str(uuid.uuid4())


def calculate_file_hash(content: bytes) -> str:
    """计算文件内容的哈希值"""
    return hashlib.md5(content).hexdigest()


def ensure_directory_exists(directory_path: str) -> str:
    """确保目录存在，如果不存在则创建"""
    path = Path(directory_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def format_error_response(
    error_message: str,
    error_code: str = None,
    request_id: str = None,
    details: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    格式化错误响应

    Args:
        error_message: 错误消息
        error_code: 错误代码
        request_id: 请求ID
        details: 详细信息

    Returns:
        格式化的错误响应字典
    """
    response = {
        "error": error_message,
        "timestamp": time.time(),
    }

    if error_code:
        response["code"] = error_code

    if request_id:
        response["request_id"] = request_id

    if details:
        response["details"] = details

    return response


def calculate_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    计算两个向量之间的余弦相似度

    Args:
        embedding1: 第一个向量
        embedding2: 第二个向量

    Returns:
        相似度分数（0-1之间）
    """
    # 归一化向量
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    # 计算余弦相似度
    similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

    # 确保在0-1范围内
    return max(0.0, min(1.0, similarity))


def bytes_to_image(content: bytes) -> Optional[np.ndarray]:
    """
    将字节转换为OpenCV图像

    Args:
        content: 图像字节

    Returns:
        OpenCV图像或None（如果转换失败）
    """
    try:
        import cv2
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def time_it(func):
    """测量函数执行时间的装饰器"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        return result, execution_time
    return wrapper


class Timer:
    """计时器上下文管理器"""

    def __init__(self, name: str = "operation"):
        self.name = name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        print(f"{self.name} took {elapsed:.2f} seconds")


# 全局logger实例
logger = setup_logging("ai-service-shared")