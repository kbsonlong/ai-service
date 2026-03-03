"""
共享配置模块
所有微服务共享的配置管理
"""

import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class ServiceConfig(BaseSettings):
    """服务基础配置"""

    # API配置
    api_key: str = Field(default="your-secret-api-key", env="API_KEY")
    service_name: str = Field(default="ai-service", env="SERVICE_NAME")

    # 服务器配置
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")

    # 日志配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")

    # 模型配置
    models_dir: str = Field(default="./models", env="MODELS_DIR")

    # 数据库配置
    database_url: str = Field(default="sqlite:///./data/service.db", env="DATABASE_URL")

    # 索引文件配置（用于人脸识别服务）
    index_file_path: str = Field(default="./data/faces.index", env="INDEX_FILE_PATH")

    # 多实例配置
    instance_role: str = Field(default="primary", env="INSTANCE_ROLE")  # primary 或 replica

    # Redis配置（用于视频服务）
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # 其他服务URL（服务间通信）
    face_service_url: str = Field(default="http://face-service:8002", env="FACE_SERVICE_URL")
    ocr_service_url: str = Field(default="http://ocr-service:8001", env="OCR_SERVICE_URL")
    video_service_url: str = Field(default="http://video-service:8003", env="VIDEO_SERVICE_URL")

    # 文件上传限制
    max_upload_size_mb: int = Field(default=10, env="MAX_UPLOAD_SIZE_MB")
    allowed_image_types: list = Field(default=["image/jpeg", "image/png", "image/jpg"], env="ALLOWED_IMAGE_TYPES")
    allowed_video_types: list = Field(default=["video/mp4", "video/mpeg"], env="ALLOWED_VIDEO_TYPES")

    # 性能配置
    max_concurrent_requests: int = Field(default=10, env="MAX_CONCURRENT_REQUESTS")
    request_timeout_seconds: int = Field(default=30, env="REQUEST_TIMEOUT_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("allowed_image_types", "allowed_video_types", pre=True)
    def parse_list(cls, v):
        """将逗号分隔的字符串转换为列表"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v

    def get_max_upload_size_bytes(self) -> int:
        """获取最大上传文件大小（字节）"""
        return self.max_upload_size_mb * 1024 * 1024


class DatabaseConfig:
    """数据库配置"""

    @staticmethod
    def get_sqlite_config(db_path: str) -> Dict[str, Any]:
        """获取SQLite配置"""
        return {
            "url": f"sqlite:///{db_path}",
            "connect_args": {"check_same_thread": False},
            "echo": False
        }


class ModelConfig:
    """模型配置"""

    # OCR模型配置
    OCR_MODEL = "rapidocr"

    # 人脸识别模型配置
    FACE_MODEL_NAME = "buffalo_l"
    FACE_DETECTION_SIZE = (640, 640)
    FACE_EMBEDDING_DIMENSION = 512
    FACE_RECOGNITION_THRESHOLD = 0.6  # 相似度阈值

    # 视频分析配置
    VIDEO_FRAME_INTERVAL_SECONDS = 1.0  # 每秒分析一帧
    VIDEO_MIN_FACE_CONFIDENCE = 0.5     # 最小人脸置信度


# 全局配置实例
config = ServiceConfig()


def get_config() -> ServiceConfig:
    """获取配置实例"""
    return config


def print_config_summary():
    """打印配置摘要（隐藏敏感信息）"""
    cfg = config.dict()

    # 隐藏敏感信息
    if "api_key" in cfg:
        cfg["api_key"] = "***" if cfg["api_key"] != "your-secret-api-key" else "default"

    if "database_url" in cfg:
        if "sqlite:///" in cfg["database_url"]:
            cfg["database_url"] = cfg["database_url"].replace("sqlite:///", "sqlite:///***")

    print("=== 服务配置摘要 ===")
    for key, value in cfg.items():
        print(f"{key}: {value}")
    print("==================")