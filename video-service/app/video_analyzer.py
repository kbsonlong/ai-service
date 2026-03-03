"""
视频分析器模块
"""

import os
import time
import cv2
import requests
import tempfile
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from shared.config import config
from shared.utils import logger, bytes_to_image
from shared.exceptions import VideoProcessingException
from .task_queue import VideoAnalysisTask, TaskQueueManager, get_task_queue_manager


class VideoAnalyzer:
    """视频分析器"""

    def __init__(self, face_service_url: Optional[str] = None):
        """
        初始化视频分析器

        Args:
            face_service_url: 人脸识别服务URL
        """
        self.face_service_url = face_service_url or config.face_service_url
        self.task_queue_manager = get_task_queue_manager()

    def analyze_video(self, video_path: str, task_id: str,
                     frame_interval_seconds: float = 1.0,
                     min_face_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """
        分析视频文件

        Args:
            video_path: 视频文件路径
            task_id: 任务ID
            frame_interval_seconds: 帧采样间隔（秒）
            min_face_confidence: 最小人脸置信度

        Returns:
            分析结果列表
        """
        logger.info("video_analysis_started",
                   task_id=task_id,
                   video_path=video_path,
                   frame_interval=frame_interval_seconds)

        if not os.path.exists(video_path):
            raise VideoProcessingException(f"Video file not found: {video_path}")

        # 获取任务并更新状态
        task = self.task_queue_manager.get_task(task_id)
        if task:
            task.start_processing()
            self.task_queue_manager.update_task(task)

        try:
            # 打开视频文件
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise VideoProcessingException("Could not open video file")

            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            logger.info("video_info_extracted",
                       task_id=task_id,
                       fps=fps,
                       total_frames=total_frames,
                       duration=duration,
                       resolution=f"{width}x{height}")

            # 计算帧采样间隔
            if frame_interval_seconds <= 0:
                frame_interval_seconds = 1.0

            frame_interval = int(fps * frame_interval_seconds)
            if frame_interval == 0:
                frame_interval = 1

            results = []
            frame_count = 0
            processed_frames = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # 采样帧
                if frame_count % frame_interval == 0:
                    timestamp = frame_count / fps

                    try:
                        # 分析当前帧
                        frame_result = self._analyze_frame(
                            frame=frame,
                            timestamp=timestamp,
                            min_face_confidence=min_face_confidence
                        )

                        if frame_result:
                            results.append(frame_result)

                        processed_frames += 1

                        # 更新任务进度
                        if task and total_frames > 0:
                            progress = frame_count / total_frames
                            task.update_progress(progress)
                            self.task_queue_manager.update_task(task)

                    except Exception as e:
                        logger.warning("frame_analysis_failed",
                                      task_id=task_id,
                                      timestamp=timestamp,
                                      error=str(e))

                frame_count += 1

                # 每处理10帧更新一次日志
                if frame_count % (frame_interval * 10) == 0:
                    logger.debug("video_analysis_progress",
                                task_id=task_id,
                                processed_frames=processed_frames,
                                total_frames=frame_count,
                                progress=f"{(frame_count / total_frames * 100):.1f}%" if total_frames > 0 else "unknown")

            cap.release()

            logger.info("video_analysis_completed",
                       task_id=task_id,
                       total_frames_processed=processed_frames,
                       total_results=len(results),
                       duration_seconds=duration)

            return results

        except Exception as e:
            logger.error("video_analysis_failed",
                        task_id=task_id,
                        error=str(e))
            raise VideoProcessingException(f"Video analysis failed: {str(e)}")

        finally:
            # 清理临时文件
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                    logger.debug("temp_video_file_cleaned",
                                task_id=task_id,
                                video_path=video_path)
            except Exception as e:
                logger.warning("temp_file_cleanup_failed",
                              task_id=task_id,
                              video_path=video_path,
                              error=str(e))

    def _analyze_frame(self, frame: cv2.Mat, timestamp: float,
                      min_face_confidence: float) -> Optional[Dict[str, Any]]:
        """
        分析单个视频帧

        Args:
            frame: 视频帧
            timestamp: 时间戳（秒）
            min_face_confidence: 最小人脸置信度

        Returns:
            分析结果，如果没有检测到人脸则返回None
        """
        try:
            # 将帧编码为JPEG
            success, encoded_image = cv2.imencode('.jpg', frame)
            if not success:
                return None

            image_bytes = encoded_image.tobytes()

            # 调用人脸识别服务
            face_result = self._call_face_service(image_bytes)
            if not face_result:
                return None

            # 提取人脸信息
            faces_detected = face_result.get("face_count", 0)
            if faces_detected == 0:
                return None

            # 处理每个人脸
            recognized_faces = []
            faces = face_result.get("faces", [])

            for face in faces:
                # 检查人脸检测置信度
                detection_score = face.get("detection_score", 0.0)
                if detection_score < min_face_confidence:
                    continue

                # 检查是否有人脸识别结果
                # 注意：这里需要根据人脸识别服务的实际响应结构调整
                if "recognition_result" in face:
                    recognition = face["recognition_result"]
                    if recognition.get("is_match", False):
                        recognized_faces.append({
                            "name": recognition.get("name"),
                            "similarity": recognition.get("similarity", 0.0),
                            "bounding_box": face.get("bounding_box", {})
                        })

            if not recognized_faces:
                return None

            return {
                "timestamp": round(timestamp, 2),
                "frame_info": {
                    "width": frame.shape[1],
                    "height": frame.shape[0],
                    "channels": frame.shape[2] if len(frame.shape) > 2 else 1
                },
                "face_detection": {
                    "faces_detected": faces_detected,
                    "detection_score_avg": sum(f.get("detection_score", 0) for f in faces) / len(faces) if faces else 0
                },
                "recognized_faces": recognized_faces
            }

        except Exception as e:
            logger.warning("frame_analysis_error",
                          timestamp=timestamp,
                          error=str(e))
            return None

    def _call_face_service(self, image_bytes: bytes) -> Optional[Dict[str, Any]]:
        """
        调用人脸识别服务

        Args:
            image_bytes: 图像字节数据

        Returns:
            人脸识别服务响应
        """
        try:
            # 准备请求
            files = {"file": ("frame.jpg", image_bytes, "image/jpeg")}
            headers = {"x-api-key": config.api_key}

            # 发送请求
            response = requests.post(
                urljoin(self.face_service_url, "/v1/face/detect"),
                files=files,
                headers=headers,
                timeout=10  # 10秒超时
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning("face_service_call_failed",
                              status_code=response.status_code,
                              response_text=response.text[:200])
                return None

        except requests.exceptions.Timeout:
            logger.warning("face_service_timeout",
                          face_service_url=self.face_service_url)
            return None
        except Exception as e:
            logger.warning("face_service_call_error",
                          error=str(e),
                          face_service_url=self.face_service_url)
            return None

    def analyze_video_from_bytes(self, video_bytes: bytes, task_id: str,
                                filename: str = "video.mp4",
                                **kwargs) -> List[Dict[str, Any]]:
        """
        从字节数据分析视频

        Args:
            video_bytes: 视频字节数据
            task_id: 任务ID
            filename: 文件名（用于确定格式）
            **kwargs: 其他参数传递给analyze_video

        Returns:
            分析结果列表
        """
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1],
                                        delete=False) as temp_file:
            temp_file.write(video_bytes)
            temp_path = temp_file.name

        try:
            return self.analyze_video(temp_path, task_id, **kwargs)
        finally:
            # 确保临时文件被清理
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass


# RQ工作进程的任务函数
def analyze_video_task(task_id: str):
    """
    RQ工作进程的任务函数

    这个函数由RQ工作进程调用，执行实际的视频分析

    Args:
        task_id: 任务ID
    """
    logger.info("rq_task_started", task_id=task_id)

    try:
        # 获取任务队列管理器
        task_queue_manager = get_task_queue_manager()
        task = task_queue_manager.get_task(task_id)

        if not task:
            logger.error("task_not_found", task_id=task_id)
            return

        # 创建视频分析器
        analyzer = VideoAnalyzer(face_service_url=task.face_service_url)

        # 执行视频分析
        results = analyzer.analyze_video(
            video_path=task.video_path,
            task_id=task_id,
            frame_interval_seconds=task.frame_interval_seconds,
            min_face_confidence=task.min_face_confidence
        )

        # 更新任务状态
        task.complete(results)
        task_queue_manager.update_task(task)

        logger.info("rq_task_completed",
                   task_id=task_id,
                   results_count=len(results))

    except Exception as e:
        logger.error("rq_task_failed",
                    task_id=task_id,
                    error=str(e))

        # 更新任务状态为失败
        try:
            task_queue_manager = get_task_queue_manager()
            task = task_queue_manager.get_task(task_id)
            if task:
                task.fail(str(e))
                task_queue_manager.update_task(task)
        except:
            pass

        raise  # 重新抛出异常以便RQ记录失败


# 全局视频分析器实例
_video_analyzer = None


def get_video_analyzer() -> VideoAnalyzer:
    """获取全局视频分析器实例"""
    global _video_analyzer
    if _video_analyzer is None:
        _video_analyzer = VideoAnalyzer()
    return _video_analyzer