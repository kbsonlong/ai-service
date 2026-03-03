"""
OCR微服务主应用
"""

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
import os

# 添加共享模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), "../../shared"))

from shared.config import config, print_config_summary
from shared.utils import setup_logging, validate_upload_file, generate_request_id
from shared.exceptions import setup_exception_handlers, FileValidationException
from .ocr_engine import OCRProcessor

# 配置日志
logger = setup_logging("ocr-service", config.log_level, config.log_format)

# 创建FastAPI应用
app = FastAPI(
    title="OCR Service",
    description="Optical Character Recognition Microservice",
    version="1.0.0",
    docs_url="/docs" if config.log_level == "DEBUG" else None,
    redoc_url="/redoc" if config.log_level == "DEBUG" else None,
)

# 设置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置全局异常处理器
setup_exception_handlers(app)

# 全局OCR处理器实例
ocr_processor = None


def get_ocr_processor():
    """获取OCR处理器实例（依赖注入）"""
    global ocr_processor
    if ocr_processor is None:
        ocr_processor = OCRProcessor()
    return ocr_processor


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info("ocr_service_starting",
                host=config.host,
                port=config.port,
                log_level=config.log_level)

    # 初始化OCR处理器
    try:
        ocr_processor = get_ocr_processor()
        logger.info("ocr_processor_initialized")
    except Exception as e:
        logger.error("ocr_processor_init_failed", error=str(e))
        raise

    # 打印配置摘要
    print_config_summary()


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("ocr_service_shutting_down")


@app.get("/")
async def root():
    """根端点"""
    return {
        "service": "OCR Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "ocr": "/v1/ocr/scan",
            "health": "/health",
            "docs": "/docs" if config.log_level == "DEBUG" else "disabled"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 检查OCR处理器状态
        ocr_processor = get_ocr_processor()
        if ocr_processor.is_ready():
            return {
                "status": "healthy",
                "service": "ocr-service",
                "model_loaded": True,
                "timestamp": os.times().user
            }
        else:
            return {
                "status": "unhealthy",
                "service": "ocr-service",
                "model_loaded": False,
                "timestamp": os.times().user
            }, 503
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "ocr-service",
            "error": str(e),
            "timestamp": os.times().user
        }, 503


@app.post("/v1/ocr/scan")
async def ocr_scan(
    file: UploadFile = File(...),
    ocr_processor: OCRProcessor = Depends(get_ocr_processor)
):
    """
    OCR文字识别端点

    上传图像文件，返回识别到的文字和位置信息
    """
    request_id = generate_request_id()
    logger.info("ocr_scan_request_received",
                request_id=request_id,
                filename=file.filename,
                content_type=file.content_type)

    try:
        # 验证上传文件
        content, file_ext = validate_upload_file(
            file=file,
            allowed_content_types=config.allowed_image_types,
            max_size_bytes=config.get_max_upload_size_bytes()
        )

        # 执行OCR识别
        results = ocr_processor.scan_image(content)

        logger.info("ocr_scan_completed",
                    request_id=request_id,
                    text_count=len(results),
                    filename=file.filename)

        return {
            "request_id": request_id,
            "results": results,
            "file_info": {
                "filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": len(content)
            }
        }

    except FileValidationException as e:
        logger.warning("file_validation_failed",
                      request_id=request_id,
                      filename=file.filename,
                      error=str(e))
        raise
    except Exception as e:
        logger.error("ocr_scan_failed",
                     request_id=request_id,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


@app.post("/v1/ocr/batch")
async def ocr_batch(
    files: list[UploadFile] = File(...),
    ocr_processor: OCRProcessor = Depends(get_ocr_processor)
):
    """
    批量OCR识别端点

    上传多个图像文件，批量进行OCR识别
    """
    request_id = generate_request_id()
    logger.info("ocr_batch_request_received",
                request_id=request_id,
                file_count=len(files))

    results = []
    for i, file in enumerate(files):
        try:
            # 验证上传文件
            content, file_ext = validate_upload_file(
                file=file,
                allowed_content_types=config.allowed_image_types,
                max_size_bytes=config.get_max_upload_size_bytes()
            )

            # 执行OCR识别
            ocr_result = ocr_processor.scan_image(content)

            results.append({
                "filename": file.filename,
                "success": True,
                "results": ocr_result,
                "file_info": {
                    "content_type": file.content_type,
                    "size_bytes": len(content)
                }
            })

        except Exception as e:
            logger.warning("batch_file_failed",
                          request_id=request_id,
                          filename=file.filename,
                          error=str(e))

            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })

    logger.info("ocr_batch_completed",
                request_id=request_id,
                total_files=len(files),
                success_count=sum(1 for r in results if r["success"]))

    return {
        "request_id": request_id,
        "total_files": len(files),
        "results": results
    }