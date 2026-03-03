"""
自定义异常类
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException, status


class AIBaseException(Exception):
    """AI服务基础异常类"""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ModelLoadException(AIBaseException):
    """模型加载异常"""

    def __init__(self, model_name: str, error: str):
        super().__init__(
            message=f"Failed to load model: {model_name}",
            error_code="MODEL_LOAD_ERROR",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"model_name": model_name, "error": error}
        )


class InvalidInputException(AIBaseException):
    """无效输入异常"""

    def __init__(self, field: str, value: Any, reason: str):
        super().__init__(
            message=f"Invalid input for field '{field}': {reason}",
            error_code="INVALID_INPUT",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"field": field, "value": str(value), "reason": reason}
        )


class FileValidationException(AIBaseException):
    """文件验证异常"""

    def __init__(self, filename: str, reason: str):
        super().__init__(
            message=f"File validation failed: {reason}",
            error_code="FILE_VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"filename": filename, "reason": reason}
        )


class FaceDetectionException(AIBaseException):
    """人脸检测异常"""

    def __init__(self, reason: str = "No face detected"):
        super().__init__(
            message=f"Face detection failed: {reason}",
            error_code="FACE_DETECTION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"reason": reason}
        )


class FaceRecognitionException(AIBaseException):
    """人脸识别异常"""

    def __init__(self, reason: str = "Face recognition failed"):
        super().__init__(
            message=f"Face recognition failed: {reason}",
            error_code="FACE_RECOGNITION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"reason": reason}
        )


class OCRProcessingException(AIBaseException):
    """OCR处理异常"""

    def __init__(self, reason: str = "OCR processing failed"):
        super().__init__(
            message=f"OCR processing failed: {reason}",
            error_code="OCR_PROCESSING_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"reason": reason}
        )


class VideoProcessingException(AIBaseException):
    """视频处理异常"""

    def __init__(self, reason: str = "Video processing failed"):
        super().__init__(
            message=f"Video processing failed: {reason}",
            error_code="VIDEO_PROCESSING_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"reason": reason}
        )


class DatabaseException(AIBaseException):
    """数据库异常"""

    def __init__(self, operation: str, error: str):
        super().__init__(
            message=f"Database operation '{operation}' failed",
            error_code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"operation": operation, "error": error}
        )


class AuthenticationException(AIBaseException):
    """认证异常"""

    def __init__(self, reason: str = "Authentication failed"):
        super().__init__(
            message=f"Authentication failed: {reason}",
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details={"reason": reason}
        )


class RateLimitException(AIBaseException):
    """速率限制异常"""

    def __init__(self, limit: int, window: str):
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window}",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"limit": limit, "window": window}
        )


def handle_ai_exception(exception: AIBaseException) -> Dict[str, Any]:
    """
    处理AI异常并返回标准化响应

    Args:
        exception: AI异常实例

    Returns:
        标准化错误响应
    """
    import time
    from shared.utils import format_error_response

    return format_error_response(
        error_message=exception.message,
        error_code=exception.error_code,
        details=exception.details
    )


def setup_exception_handlers(app):
    """
    设置全局异常处理器

    Args:
        app: FastAPI应用实例
    """
    from fastapi.responses import JSONResponse

    @app.exception_handler(AIBaseException)
    async def ai_exception_handler(request, exc: AIBaseException):
        """处理AI基础异常"""
        error_response = handle_ai_exception(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        """处理HTTP异常"""
        import time
        from shared.utils import format_error_response

        error_response = format_error_response(
            error_message=exc.detail,
            error_code="HTTP_ERROR"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        """处理通用异常"""
        import time
        from shared.utils import format_error_response

        # 记录详细错误信息
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)

        error_response = format_error_response(
            error_message="Internal server error",
            error_code="INTERNAL_SERVER_ERROR"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response
        )