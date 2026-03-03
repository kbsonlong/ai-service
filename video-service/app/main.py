"""
视频分析微服务主应用
"""

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

import sys
import os
import uuid
import tempfile

# 添加共享模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), "../../shared"))

from shared.config import config, print_config_summary
from shared.utils import setup_logging, validate_upload_file, generate_request_id
from shared.exceptions import setup_exception_handlers, FileValidationException
from .task_queue import VideoAnalysisTask, TaskQueueManager, TaskStatus, get_task_queue_manager
from .video_analyzer import get_video_analyzer

# 配置日志
logger = setup_logging("video-service", config.log_level, config.log_format)

# 创建FastAPI应用
app = FastAPI(
    title="Video Analysis Service",
    description="Video Face Detection and Analysis Microservice",
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


def get_task_queue():
    """获取任务队列管理器实例（依赖注入）"""
    return get_task_queue_manager()


def get_video_analyzer_instance():
    """获取视频分析器实例（依赖注入）"""
    return get_video_analyzer()


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info("video_service_starting",
                host=config.host,
                port=config.port,
                log_level=config.log_level)

    try:
        # 初始化任务队列管理器
        task_queue = get_task_queue()
        if task_queue.is_connected():
            queue_stats = task_queue.get_queue_stats()
            logger.info("task_queue_initialized", **queue_stats)
        else:
            logger.error("task_queue_connection_failed")
            # 注意：队列连接失败不是致命错误，服务仍然可以运行（某些功能受限）

        # 打印配置摘要
        print_config_summary()

    except Exception as e:
        logger.error("video_service_startup_failed", error=str(e))
        # 不抛出异常，让服务继续运行（但某些功能可能不可用）


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("video_service_shutting_down")

    # 清理旧任务
    try:
        task_queue = get_task_queue()
        if task_queue.is_connected():
            cleaned_count = task_queue.cleanup_old_tasks(older_than_hours=24)
            if cleaned_count > 0:
                logger.info("old_tasks_cleaned_on_shutdown", count=cleaned_count)
    except Exception as e:
        logger.warning("cleanup_on_shutdown_failed", error=str(e))


@app.get("/")
async def root():
    """根端点"""
    task_queue = get_task_queue()
    queue_stats = task_queue.get_queue_stats() if task_queue else {"connected": False}

    return {
        "service": "Video Analysis Service",
        "version": "1.0.0",
        "status": "running",
        "task_queue": queue_stats,
        "dependencies": {
            "face_service_url": config.face_service_url,
            "redis_url": config.redis_url
        },
        "endpoints": {
            "analyze": "/v1/video/analyze",
            "task_status": "/v1/video/status/{task_id}",
            "cancel_task": "/v1/video/cancel/{task_id}",
            "queue_stats": "/v1/video/queue-stats",
            "health": "/health",
            "docs": "/docs" if config.log_level == "DEBUG" else "disabled"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        task_queue = get_task_queue()
        queue_connected = task_queue.is_connected() if task_queue else False

        # 检查人脸识别服务连接
        face_service_healthy = False
        try:
            import requests
            response = requests.get(
                f"{config.face_service_url}/health",
                timeout=3,
                headers={"x-api-key": config.api_key}
            )
            face_service_healthy = response.status_code == 200
        except:
            pass

        health_status = "healthy" if queue_connected else "degraded"

        return {
            "status": health_status,
            "service": "video-service",
            "components": {
                "task_queue": queue_connected,
                "face_service": face_service_healthy
            },
            "timestamp": os.times().user
        }

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "video-service",
            "error": str(e),
            "timestamp": os.times().user
        }, 503


@app.post("/v1/video/analyze")
async def video_analyze(
    file: UploadFile = File(...),
    frame_interval_seconds: float = 1.0,
    min_face_confidence: float = 0.5,
    task_queue: TaskQueueManager = Depends(get_task_queue)
):
    """
    视频分析端点

    上传视频文件，异步进行人脸识别分析
    """
    request_id = generate_request_id()
    logger.info("video_analyze_request_received",
                request_id=request_id,
                filename=file.filename,
                content_type=file.content_type,
                frame_interval=frame_interval_seconds,
                min_confidence=min_face_confidence)

    if not task_queue.is_connected():
        raise HTTPException(
            status_code=503,
            detail="Task queue is not available. Please try again later."
        )

    try:
        # 验证上传文件
        content, file_ext = validate_upload_file(
            file=file,
            allowed_content_types=config.allowed_video_types,
            max_size_bytes=config.get_max_upload_size_bytes() * 10  # 视频文件允许更大
        )

        # 创建临时文件保存视频
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
            temp_file.write(content)
            video_path = temp_file.name

        # 创建任务
        task_id = str(uuid.uuid4())
        task = VideoAnalysisTask(
            task_id=task_id,
            video_path=video_path,
            face_service_url=config.face_service_url,
            frame_interval_seconds=frame_interval_seconds,
            min_face_confidence=min_face_confidence
        )

        # 添加文件信息到元数据
        task.metadata.update({
            "original_filename": file.filename,
            "content_type": file.content_type,
            "file_size_bytes": len(content),
            "file_extension": file_ext
        })

        # 提交任务到队列
        submitted_task_id = task_queue.submit_task(task)

        logger.info("video_analyze_task_submitted",
                    request_id=request_id,
                    task_id=submitted_task_id,
                    video_path=video_path)

        return {
            "request_id": request_id,
            "task_id": submitted_task_id,
            "status": TaskStatus.PENDING,
            "message": "Video analysis task submitted successfully",
            "estimated_processing_time": "Varies based on video length",
            "check_status_url": f"/v1/video/status/{submitted_task_id}"
        }

    except FileValidationException as e:
        logger.warning("file_validation_failed",
                      request_id=request_id,
                      filename=file.filename,
                      error=str(e))
        raise
    except Exception as e:
        logger.error("video_analyze_failed",
                     request_id=request_id,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to submit video analysis task: {str(e)}")


@app.get("/v1/video/status/{task_id}")
async def get_task_status(
    task_id: str,
    task_queue: TaskQueueManager = Depends(get_task_queue)
):
    """获取任务状态"""
    request_id = generate_request_id()
    logger.info("get_task_status_request",
                request_id=request_id,
                task_id=task_id)

    try:
        task = task_queue.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        response = {
            "request_id": request_id,
            "task_id": task_id,
            "status": task.status,
            "progress": task.progress,
            "metadata": task.metadata,
            "configuration": {
                "frame_interval_seconds": task.frame_interval_seconds,
                "min_face_confidence": task.min_face_confidence
            },
            "timestamps": task.to_dict()["timestamps"]
        }

        # 如果任务完成或失败，添加结果或错误信息
        if task.status == TaskStatus.COMPLETED:
            response["results"] = task.results
            response["results_count"] = len(task.results)
        elif task.status == TaskStatus.FAILED:
            response["error"] = task.error

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_task_status_failed",
                     request_id=request_id,
                     task_id=task_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@app.post("/v1/video/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    task_queue: TaskQueueManager = Depends(get_task_queue)
):
    """取消任务"""
    request_id = generate_request_id()
    logger.info("cancel_task_request",
                request_id=request_id,
                task_id=task_id)

    try:
        success = task_queue.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found or cannot be cancelled")

        return {
            "request_id": request_id,
            "task_id": task_id,
            "success": True,
            "message": "Task cancelled successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("cancel_task_failed",
                     request_id=request_id,
                     task_id=task_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@app.get("/v1/video/queue-stats")
async def get_queue_stats(
    task_queue: TaskQueueManager = Depends(get_task_queue)
):
    """获取队列统计信息"""
    request_id = generate_request_id()
    logger.info("get_queue_stats_request", request_id=request_id)

    try:
        stats = task_queue.get_queue_stats()
        return {
            "request_id": request_id,
            "queue_stats": stats
        }
    except Exception as e:
        logger.error("get_queue_stats_failed",
                     request_id=request_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get queue stats: {str(e)}")


@app.post("/v1/video/analyze-sync")
async def video_analyze_sync(
    file: UploadFile = File(...),
    frame_interval_seconds: float = 1.0,
    min_face_confidence: float = 0.5,
    video_analyzer=Depends(get_video_analyzer_instance)
):
    """
    同步视频分析端点（仅用于测试和小视频）

    警告：对于大视频，这会阻塞请求直到分析完成
    """
    request_id = generate_request_id()
    logger.info("video_analyze_sync_request_received",
                request_id=request_id,
                filename=file.filename)

    try:
        # 验证上传文件（限制更小的大小）
        content, file_ext = validate_upload_file(
            file=file,
            allowed_content_types=config.allowed_video_types,
            max_size_bytes=50 * 1024 * 1024  # 同步处理限制为50MB
        )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 执行同步分析
        results = video_analyzer.analyze_video_from_bytes(
            video_bytes=content,
            task_id=task_id,
            filename=file.filename,
            frame_interval_seconds=frame_interval_seconds,
            min_face_confidence=min_face_confidence
        )

        logger.info("video_analyze_sync_completed",
                    request_id=request_id,
                    task_id=task_id,
                    results_count=len(results))

        return {
            "request_id": request_id,
            "task_id": task_id,
            "status": "completed",
            "results": results,
            "results_count": len(results),
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
        logger.error("video_analyze_sync_failed",
                     request_id=request_id,
                     filename=file.filename,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {str(e)}")


@app.get("/v1/video/pending-tasks")
async def get_pending_tasks(
    limit: int = 20,
    task_queue: TaskQueueManager = Depends(get_task_queue)
):
    """获取待处理任务列表"""
    request_id = generate_request_id()
    logger.info("get_pending_tasks_request",
                request_id=request_id,
                limit=limit)

    try:
        # 注意：这个实现需要扫描所有任务键
        # 在生产环境中，应该使用更高效的方法
        task_keys = task_queue.redis_conn.keys("video_task:*") if task_queue.is_connected() else []
        pending_tasks = []

        for task_key in task_keys[:limit]:
            try:
                task_data = task_queue.redis_conn.get(task_key)
                if task_data:
                    import json
                    task_dict = json.loads(task_data)
                    if task_dict.get("status") in ["pending", "processing"]:
                        pending_tasks.append({
                            "task_id": task_dict.get("task_id"),
                            "status": task_dict.get("status"),
                            "progress": task_dict.get("progress", 0.0),
                            "metadata": task_dict.get("metadata", {}),
                            "created_at": task_dict.get("timestamps", {}).get("created_at")
                        })
            except:
                continue

        return {
            "request_id": request_id,
            "pending_tasks": pending_tasks,
            "total_pending": len(pending_tasks),
            "limit": limit
        }

    except Exception as e:
        logger.error("get_pending_tasks_failed",
                     request_id=request_id,
                     error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get pending tasks: {str(e)}")