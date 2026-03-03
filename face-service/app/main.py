"""
人脸识别微服务主应用
"""

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
import os

# 添加共享模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), "../../shared"))

from shared.config import config, print_config_summary
from shared.utils import setup_logging, validate_upload_file, generate_request_id
from shared.exceptions import setup_exception_handlers, FileValidationException
from shared.memory_monitor import start_memory_monitoring, get_memory_status
from .face_engine import FaceRecognitionEngine, get_face_engine
from .database import FaceDatabase, get_face_database

# Prometheus监控
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge

# 配置日志
logger = setup_logging("face-service", config.log_level, config.log_format)

# 创建FastAPI应用
app = FastAPI(
    title="Face Recognition Service",
    description="Face Detection and Recognition Microservice",
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

# 设置Prometheus指标
if config.log_level == "DEBUG" or True:  # 始终启用指标
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# 设置全局异常处理器
setup_exception_handlers(app)


def get_face_recognition_engine():
    """获取人脸识别引擎实例（依赖注入）"""
    return get_face_engine()


def get_face_database_instance():
    """获取人脸数据库实例（依赖注入）"""
    return get_face_database()


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info("face_service_starting",
                host=config.host,
                port=config.port,
                log_level=config.log_level)

    try:
        # 初始化人脸识别引擎
        face_engine = get_face_recognition_engine()
        if face_engine.is_ready():
            logger.info("face_engine_initialized",
                       total_faces=face_engine.index.ntotal if face_engine.index else 0)
        else:
            logger.error("face_engine_init_failed")
            raise RuntimeError("Face recognition engine failed to initialize")

        # 初始化数据库
        face_db = get_face_database_instance()
        stats = face_db.get_statistics()
        logger.info("face_database_initialized", **stats)

        # 启动内存监控
        memory_monitor = start_memory_monitoring(
            warning_threshold_percent=80.0,
            critical_threshold_percent=90.0,
            process_memory_limit_mb=1024,  # 限制进程使用1GB内存
            check_interval_seconds=60
        )
        logger.info("memory_monitor_started")

        # 打印配置摘要
        print_config_summary()

    except Exception as e:
        logger.error("face_service_startup_failed", error=str(e))
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("face_service_shutting_down")

    # 保存FAISS索引
    try:
        face_engine = get_face_recognition_engine()
        if hasattr(face_engine, 'save_index') and hasattr(face_engine, 'index_path'):
            if face_engine.save_index(face_engine.index_path):
                logger.info("faiss_index_saved_on_shutdown", index_path=face_engine.index_path)
            else:
                logger.warning("faiss_index_save_failed_on_shutdown", index_path=face_engine.index_path)
    except Exception as e:
        logger.warning("save_index_on_shutdown_failed", error=str(e))


@app.get("/")
async def root():
    """根端点"""
    face_engine = get_face_recognition_engine()
    face_db = get_face_database_instance()

    stats = face_db.get_statistics()

    return {
        "service": "Face Recognition Service",
        "version": "1.0.0",
        "status": "running",
        "statistics": stats,
        "engine_info": face_engine.get_engine_info(),
        "endpoints": {
            "detect": "/v1/face/detect",
            "register": "/v1/face/register",
            "recognize": "/v1/face/recognize",
            "recognize_multiple": "/v1/face/recognize-multiple",
            "registered_faces": "/v1/face/registered",
            "health": "/health",
            "docs": "/docs" if config.log_level == "DEBUG" else "disabled"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        face_engine = get_face_recognition_engine()
        face_db = get_face_database_instance()

        engine_ready = face_engine.is_ready()

        # 简单数据库连接测试
        db_stats = face_db.get_statistics()

        if engine_ready:
            return {
                "status": "healthy",
                "service": "face-service",
                "engine_ready": True,
                "database_connected": True,
                "registered_faces": db_stats["total_faces"],
                "timestamp": os.times().user
            }
        else:
            return {
                "status": "unhealthy",
                "service": "face-service",
                "engine_ready": False,
                "database_connected": True,
                "error": "Face recognition engine not ready",
                "timestamp": os.times().user
            }, 503

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "face-service",
            "error": str(e),
            "timestamp": os.times().user
        }, 503


@app.post("/v1/face/detect")
async def face_detect(
    file: UploadFile = File(...),
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """
    人脸检测端点

    上传图像文件，返回检测到的人脸信息（不进行识别）
    """
    request_id = generate_request_id()
    logger.info("face_detect_request_received",
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

        # 执行人脸检测
        faces = face_engine.detect_faces(content)

        logger.info("face_detect_completed",
                    request_id=request_id,
                    face_count=len(faces),
                    filename=file.filename)

        return {
            "request_id": request_id,
            "face_count": len(faces),
            "faces": faces,
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
        logger.error("face_detect_failed",
                     request_id=request_id,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Face detection failed: {str(e)}")


@app.post("/v1/face/register")
async def face_register(
    name: str = Form(...),
    file: UploadFile = File(...),
    metadata: str = Form(None),
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """
    人脸注册端点

    上传包含人脸的图像，注册新的人脸
    """
    request_id = generate_request_id()
    logger.info("face_register_request_received",
                request_id=request_id,
                name=name,
                filename=file.filename)

    try:
        # 验证上传文件
        content, file_ext = validate_upload_file(
            file=file,
            allowed_content_types=config.allowed_image_types,
            max_size_bytes=config.get_max_upload_size_bytes()
        )

        # 解析元数据（如果提供）
        metadata_dict = None
        if metadata:
            try:
                import json
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning("metadata_json_decode_failed",
                              request_id=request_id,
                              metadata=metadata)

        # 执行人脸注册
        result = face_engine.register_face(content, name, metadata_dict)

        logger.info("face_register_completed",
                    request_id=request_id,
                    name=name,
                    face_id=result.get("face_id"),
                    embedding_id=result.get("embedding_id"))

        return {
            "request_id": request_id,
            "success": True,
            "result": result
        }

    except FileValidationException as e:
        logger.warning("file_validation_failed",
                      request_id=request_id,
                      filename=file.filename,
                      error=str(e))
        raise
    except Exception as e:
        logger.error("face_register_failed",
                     request_id=request_id,
                     name=name,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=400, detail=f"Face registration failed: {str(e)}")


@app.post("/v1/face/recognize")
async def face_recognize(
    file: UploadFile = File(...),
    confidence_threshold: float = Form(None),
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """
    人脸识别端点

    上传包含人脸的图像，识别已注册的人脸
    """
    request_id = generate_request_id()
    logger.info("face_recognize_request_received",
                request_id=request_id,
                filename=file.filename,
                confidence_threshold=confidence_threshold)

    try:
        # 验证上传文件
        content, file_ext = validate_upload_file(
            file=file,
            allowed_content_types=config.allowed_image_types,
            max_size_bytes=config.get_max_upload_size_bytes()
        )

        # 执行人脸识别
        result = face_engine.recognize_face(content, confidence_threshold)

        # 提取识别结果
        best_match = result.get("best_match")
        if best_match:
            recognition_status = "recognized"
            recognized_name = best_match["name"]
            similarity = best_match["similarity"]
        else:
            recognition_status = "unknown"
            recognized_name = None
            similarity = 0.0

        logger.info("face_recognize_completed",
                    request_id=request_id,
                    status=recognition_status,
                    name=recognized_name,
                    similarity=similarity)

        return {
            "request_id": request_id,
            "recognition_status": recognition_status,
            "recognized_name": recognized_name,
            "similarity": similarity,
            "result": result
        }

    except FileValidationException as e:
        logger.warning("file_validation_failed",
                      request_id=request_id,
                      filename=file.filename,
                      error=str(e))
        raise
    except Exception as e:
        logger.error("face_recognize_failed",
                     request_id=request_id,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=400, detail=f"Face recognition failed: {str(e)}")


@app.post("/v1/face/recognize-multiple")
async def recognize_multiple_faces(
    file: UploadFile = File(...),
    confidence_threshold: float = Form(None),
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """
    多个人脸识别端点

    上传图像，识别图像中的所有已注册人脸
    """
    request_id = generate_request_id()
    logger.info("multiple_faces_recognize_request_received",
                request_id=request_id,
                filename=file.filename)

    try:
        # 验证上传文件
        content, file_ext = validate_upload_file(
            file=file,
            allowed_content_types=config.allowed_image_types,
            max_size_bytes=config.get_max_upload_size_bytes()
        )

        # 执行多个人脸识别
        results = face_engine.recognize_multiple_faces(content, confidence_threshold)

        # 统计识别结果
        recognized_faces = []
        for result in results:
            best_match = result.get("best_match")
            if best_match:
                recognized_faces.append({
                    "face_index": result["face_index"],
                    "name": best_match["name"],
                    "similarity": best_match["similarity"]
                })

        logger.info("multiple_faces_recognize_completed",
                    request_id=request_id,
                    total_faces=len(results),
                    recognized_faces=len(recognized_faces))

        return {
            "request_id": request_id,
            "total_faces_detected": len(results),
            "recognized_faces": recognized_faces,
            "results": results
        }

    except FileValidationException as e:
        logger.warning("file_validation_failed",
                      request_id=request_id,
                      filename=file.filename,
                      error=str(e))
        raise
    except Exception as e:
        logger.error("multiple_faces_recognize_failed",
                     request_id=request_id,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=400, detail=f"Multiple faces recognition failed: {str(e)}")


@app.get("/v1/face/registered")
async def get_registered_faces(
    limit: int = 100,
    offset: int = 0,
    face_db: FaceDatabase = Depends(get_face_database_instance)
):
    """获取已注册的人脸列表"""
    request_id = generate_request_id()
    logger.info("get_registered_faces_request",
                request_id=request_id,
                limit=limit,
                offset=offset)

    try:
        faces = face_db.get_all_faces(limit=limit, offset=offset)
        stats = face_db.get_statistics()

        return {
            "request_id": request_id,
            "faces": faces,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": stats["total_faces"]
            },
            "statistics": stats
        }

    except Exception as e:
        logger.error("get_registered_faces_failed",
                     request_id=request_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get registered faces: {str(e)}")


@app.delete("/v1/face/{face_id}")
async def delete_face(
    face_id: int,
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """删除已注册的人脸"""
    request_id = generate_request_id()
    logger.info("delete_face_request",
                request_id=request_id,
                face_id=face_id)

    try:
        success = face_engine.delete_face(face_id)

        if success:
            return {
                "request_id": request_id,
                "success": True,
                "message": f"Face {face_id} deleted successfully"
            }
        else:
            raise HTTPException(status_code=404, detail=f"Face {face_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_face_failed",
                     request_id=request_id,
                     face_id=face_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete face: {str(e)}")


@app.get("/v1/face/search")
async def search_faces(
    name: str,
    limit: int = 20,
    face_db: FaceDatabase = Depends(get_face_database_instance)
):
    """搜索人脸记录"""
    request_id = generate_request_id()
    logger.info("search_faces_request",
                request_id=request_id,
                name=name,
                limit=limit)

    try:
        # 添加通配符以支持模糊搜索
        name_pattern = f"%{name}%"
        faces = face_db.search_faces(name_pattern, limit)

        return {
            "request_id": request_id,
            "search_query": name,
            "results": faces,
            "count": len(faces)
        }

    except Exception as e:
        logger.error("search_faces_failed",
                     request_id=request_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to search faces: {str(e)}")


@app.post("/v1/face/batch-detect")
async def face_batch_detect(
    files: list[UploadFile] = File(...),
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """
    批量人脸检测端点

    上传多个图像文件，批量进行人脸检测（不进行识别）
    """
    request_id = generate_request_id()
    logger.info("face_batch_detect_request_received",
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

            # 执行人脸检测
            faces = face_engine.detect_faces(content)

            results.append({
                "filename": file.filename,
                "success": True,
                "face_count": len(faces),
                "faces": faces,
                "file_info": {
                    "content_type": file.content_type,
                    "size_bytes": len(content)
                }
            })

        except Exception as e:
            logger.warning("batch_detect_file_failed",
                          request_id=request_id,
                          filename=file.filename,
                          error=str(e))

            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })

    logger.info("face_batch_detect_completed",
                request_id=request_id,
                total_files=len(files),
                success_count=sum(1 for r in results if r["success"]))

    return {
        "request_id": request_id,
        "total_files": len(files),
        "success_count": sum(1 for r in results if r["success"]),
        "fail_count": sum(1 for r in results if not r["success"]),
        "results": results
    }


@app.get("/v1/face/memory-status")
async def get_memory_status_endpoint():
    """获取内存状态"""
    request_id = generate_request_id()
    try:
        status = get_memory_status()
        return {
            "request_id": request_id,
            "status": "success",
            "memory_status": status
        }
    except Exception as e:
        logger.error("get_memory_status_failed",
                    request_id=request_id,
                    error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get memory status: {str(e)}")


@app.post("/v1/face/batch-recognize")
async def face_batch_recognize(
    files: list[UploadFile] = File(...),
    confidence_threshold: float = Form(None),
    face_engine: FaceRecognitionEngine = Depends(get_face_recognition_engine)
):
    """
    批量人脸识别端点

    上传多个图像文件，批量进行人脸识别
    """
    request_id = generate_request_id()
    logger.info("face_batch_recognize_request_received",
                request_id=request_id,
                file_count=len(files),
                confidence_threshold=confidence_threshold)

    results = []
    for i, file in enumerate(files):
        try:
            # 验证上传文件
            content, file_ext = validate_upload_file(
                file=file,
                allowed_content_types=config.allowed_image_types,
                max_size_bytes=config.get_max_upload_size_bytes()
            )

            # 执行人脸识别
            result = face_engine.recognize_face(content, confidence_threshold)

            # 提取识别结果
            best_match = result.get("best_match")
            if best_match:
                recognition_status = "recognized"
                recognized_name = best_match["name"]
                similarity = best_match["similarity"]
            else:
                recognition_status = "unknown"
                recognized_name = None
                similarity = 0.0

            results.append({
                "filename": file.filename,
                "success": True,
                "recognition_status": recognition_status,
                "recognized_name": recognized_name,
                "similarity": similarity,
                "result": result,
                "file_info": {
                    "content_type": file.content_type,
                    "size_bytes": len(content)
                }
            })

        except Exception as e:
            logger.warning("batch_recognize_file_failed",
                          request_id=request_id,
                          filename=file.filename,
                          error=str(e))

            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })

    logger.info("face_batch_recognize_completed",
                request_id=request_id,
                total_files=len(files),
                success_count=sum(1 for r in results if r["success"]))

    return {
        "request_id": request_id,
        "total_files": len(files),
        "success_count": sum(1 for r in results if r["success"]),
        "fail_count": sum(1 for r in results if not r["success"]),
        "results": results
    }