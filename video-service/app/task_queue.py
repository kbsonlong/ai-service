"""
视频分析任务队列模块
"""

import os
import json
import uuid
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

import redis
from rq import Queue, Worker
from rq.job import Job

from shared.config import config
from shared.utils import logger, ensure_directory_exists


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoAnalysisTask:
    """视频分析任务"""

    def __init__(self, task_id: str, video_path: str,
                 face_service_url: Optional[str] = None,
                 frame_interval_seconds: float = 1.0,
                 min_face_confidence: float = 0.5):
        """
        初始化视频分析任务

        Args:
            task_id: 任务ID
            video_path: 视频文件路径
            face_service_url: 人脸识别服务URL
            frame_interval_seconds: 帧采样间隔（秒）
            min_face_confidence: 最小人脸置信度
        """
        self.task_id = task_id
        self.video_path = video_path
        self.face_service_url = face_service_url or config.face_service_url
        self.frame_interval_seconds = frame_interval_seconds
        self.min_face_confidence = min_face_confidence

        self.status = TaskStatus.PENDING
        self.progress = 0.0  # 0.0 - 1.0
        self.results = []
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None

        # 任务元数据
        self.metadata = {
            "original_filename": os.path.basename(video_path) if video_path else "unknown",
            "file_size": os.path.getsize(video_path) if video_path and os.path.exists(video_path) else 0,
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "results": self.results,
            "error": self.error,
            "metadata": self.metadata,
            "timestamps": {
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            },
            "configuration": {
                "face_service_url": self.face_service_url,
                "frame_interval_seconds": self.frame_interval_seconds,
                "min_face_confidence": self.min_face_confidence,
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VideoAnalysisTask':
        """从字典创建任务"""
        task = cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            video_path=data.get("video_path", ""),
            face_service_url=data.get("configuration", {}).get("face_service_url"),
            frame_interval_seconds=data.get("configuration", {}).get("frame_interval_seconds", 1.0),
            min_face_confidence=data.get("configuration", {}).get("min_face_confidence", 0.5)
        )

        # 恢复状态
        task.status = TaskStatus(data.get("status", TaskStatus.PENDING))
        task.progress = data.get("progress", 0.0)
        task.results = data.get("results", [])
        task.error = data.get("error")

        # 恢复时间戳
        timestamps = data.get("timestamps", {})
        if timestamps.get("created_at"):
            task.created_at = datetime.fromisoformat(timestamps["created_at"])
        if timestamps.get("started_at"):
            task.started_at = datetime.fromisoformat(timestamps["started_at"])
        if timestamps.get("completed_at"):
            task.completed_at = datetime.fromisoformat(timestamps["completed_at"])

        task.metadata = data.get("metadata", {})

        return task

    def update_progress(self, progress: float):
        """更新进度"""
        self.progress = max(0.0, min(1.0, progress))

    def start_processing(self):
        """标记任务开始处理"""
        self.status = TaskStatus.PROCESSING
        self.started_at = datetime.now()
        self.progress = 0.0

    def complete(self, results: List[Dict[str, Any]] = None):
        """标记任务完成"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress = 1.0
        self.results = results or []

    def fail(self, error: str):
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now()
        self.error = error

    def cancel(self):
        """取消任务"""
        if self.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            self.status = TaskStatus.CANCELLED
            self.completed_at = datetime.now()


class TaskQueueManager:
    """任务队列管理器"""

    def __init__(self, redis_url: Optional[str] = None):
        """
        初始化任务队列管理器

        Args:
            redis_url: Redis连接URL
        """
        self.redis_url = redis_url or config.redis_url
        self.redis_conn = None
        self.queue = None
        self._connect()

    def _connect(self):
        """连接到Redis"""
        try:
            self.redis_conn = redis.from_url(self.redis_url)
            self.redis_conn.ping()  # 测试连接
            self.queue = Queue(connection=self.redis_conn, name="video_analysis")

            logger.info("task_queue_connected",
                       redis_url=self.redis_url,
                       queue_name="video_analysis")

        except Exception as e:
            logger.error("task_queue_connection_failed",
                        error=str(e),
                        redis_url=self.redis_url)
            raise

    def is_connected(self) -> bool:
        """检查是否连接到Redis"""
        try:
            if self.redis_conn:
                self.redis_conn.ping()
                return True
            return False
        except:
            return False

    def submit_task(self, task: VideoAnalysisTask) -> str:
        """
        提交任务到队列

        Args:
            task: 视频分析任务

        Returns:
            任务ID
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Redis")

        try:
            # 将任务存储到Redis
            task_key = f"video_task:{task.task_id}"
            task_data = json.dumps(task.to_dict())

            self.redis_conn.setex(task_key, 86400, task_data)  # 24小时过期

            # 将任务ID放入队列
            self.queue.enqueue(
                "app.video_analyzer.analyze_video_task",
                task_id=task.task_id,
                job_id=task.task_id,
                result_ttl=86400,  # 结果保留24小时
                failure_ttl=86400,  # 失败信息保留24小时
                timeout=3600  # 1小时超时
            )

            logger.info("video_task_submitted",
                       task_id=task.task_id,
                       video_path=task.video_path,
                       queue_size=self.queue.count)

            return task.task_id

        except Exception as e:
            logger.error("submit_task_failed",
                        error=str(e),
                        task_id=task.task_id)
            raise

    def get_task(self, task_id: str) -> Optional[VideoAnalysisTask]:
        """
        获取任务信息

        Args:
            task_id: 任务ID

        Returns:
            视频分析任务，如果不存在则返回None
        """
        if not self.is_connected():
            return None

        try:
            task_key = f"video_task:{task_id}"
            task_data = self.redis_conn.get(task_key)

            if task_data:
                task_dict = json.loads(task_data)
                return VideoAnalysisTask.from_dict(task_dict)

            return None

        except Exception as e:
            logger.error("get_task_failed",
                        error=str(e),
                        task_id=task_id)
            return None

    def update_task(self, task: VideoAnalysisTask) -> bool:
        """
        更新任务信息

        Args:
            task: 视频分析任务

        Returns:
            是否成功更新
        """
        if not self.is_connected():
            return False

        try:
            task_key = f"video_task:{task.task_id}"
            task_data = json.dumps(task.to_dict())

            # 更新任务数据
            self.redis_conn.setex(task_key, 86400, task_data)

            logger.debug("task_updated",
                        task_id=task.task_id,
                        status=task.status,
                        progress=task.progress)

            return True

        except Exception as e:
            logger.error("update_task_failed",
                        error=str(e),
                        task_id=task.task_id)
            return False

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        try:
            task = self.get_task(task_id)
            if not task:
                return False

            # 更新任务状态
            task.cancel()
            self.update_task(task)

            # 尝试从队列中移除任务
            try:
                job = Job.fetch(task_id, connection=self.redis_conn)
                if job:
                    job.cancel()
            except:
                pass  # 任务可能已经在处理中

            logger.info("task_cancelled", task_id=task_id)
            return True

        except Exception as e:
            logger.error("cancel_task_failed",
                        error=str(e),
                        task_id=task_id)
            return False

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        if not self.is_connected():
            return {"connected": False}

        try:
            return {
                "connected": True,
                "queue_name": self.queue.name,
                "queue_size": self.queue.count,
                "redis_url": self.redis_url,
                "workers": self._get_worker_count()
            }
        except Exception as e:
            logger.error("get_queue_stats_failed", error=str(e))
            return {"connected": False, "error": str(e)}

    def _get_worker_count(self) -> int:
        """获取工作进程数量"""
        try:
            workers = Worker.all(connection=self.redis_conn)
            return len(workers)
        except:
            return 0

    def cleanup_old_tasks(self, older_than_hours: int = 24) -> int:
        """
        清理旧任务

        Args:
            older_than_hours: 清理多少小时前的任务

        Returns:
            清理的任务数量
        """
        if not self.is_connected():
            return 0

        try:
            # 查找所有任务键
            task_keys = self.redis_conn.keys("video_task:*")

            cleaned_count = 0
            cutoff_time = time.time() - (older_than_hours * 3600)

            for task_key in task_keys:
                try:
                    task_data = self.redis_conn.get(task_key)
                    if task_data:
                        task_dict = json.loads(task_data)
                        timestamps = task_dict.get("timestamps", {})

                        completed_at = timestamps.get("completed_at")
                        if completed_at:
                            completed_time = datetime.fromisoformat(completed_at).timestamp()
                            if completed_time < cutoff_time:
                                self.redis_conn.delete(task_key)
                                cleaned_count += 1
                except:
                    continue

            logger.info("old_tasks_cleaned",
                       count=cleaned_count,
                       older_than_hours=older_than_hours)

            return cleaned_count

        except Exception as e:
            logger.error("cleanup_old_tasks_failed", error=str(e))
            return 0


# 全局任务队列管理器实例
_task_queue_manager = None


def get_task_queue_manager() -> TaskQueueManager:
    """获取全局任务队列管理器实例"""
    global _task_queue_manager
    if _task_queue_manager is None:
        _task_queue_manager = TaskQueueManager()
    return _task_queue_manager