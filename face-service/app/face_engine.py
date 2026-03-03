"""
人脸识别引擎模块
"""

import os
import time
import json
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import cv2
import faiss
from insightface.app import FaceAnalysis

from shared.config import config
from shared.utils import logger, bytes_to_image, calculate_similarity
from shared.exceptions import FaceDetectionException, FaceRecognitionException
from shared.cache import cached, get_cache
from .database import get_face_database


class FaceRecognitionEngine:
    """人脸识别引擎"""

    def __init__(self, model_name: Optional[str] = None, models_dir: Optional[str] = None,
                 index_path: Optional[str] = None, instance_role: Optional[str] = None):
        """
        初始化人脸识别引擎

        Args:
            model_name: 模型名称，如果为None则使用配置中的名称
            models_dir: 模型目录，如果为None则使用配置中的目录
            index_path: FAISS索引文件路径，如果为None则使用默认路径
            instance_role: 实例角色，如果为None则使用配置中的角色
        """
        self.model_name = model_name or config.FACE_MODEL_NAME
        self.models_dir = models_dir or config.models_dir
        self.det_size = config.FACE_DETECTION_SIZE
        self.embedding_dimension = config.FACE_EMBEDDING_DIMENSION
        self.recognition_threshold = config.FACE_RECOGNITION_THRESHOLD
        self.instance_role = instance_role or config.instance_role  # primary 或 replica
        self.readonly = (self.instance_role == "replica")

        # 设置索引文件路径
        if index_path is None:
            # 使用配置中的索引文件路径
            self.index_path = config.index_file_path
        else:
            self.index_path = index_path

        # 确保索引文件目录存在
        index_dir = os.path.dirname(self.index_path)
        if index_dir:
            from shared.utils import ensure_directory_exists
            ensure_directory_exists(index_dir)

        self.face_app = None
        self.index = None
        self.face_database = None
        self.initialized = False
        self.init_time = None

        self._initialize()

    def _initialize(self):
        """初始化人脸识别引擎"""
        try:
            start_time = time.time()
            logger.info("face_engine_initializing",
                       model_name=self.model_name,
                       models_dir=self.models_dir)

            # 初始化InsightFace
            self.face_app = FaceAnalysis(name=self.model_name, root=self.models_dir)
            self.face_app.prepare(ctx_id=0, det_size=self.det_size)

            # 获取数据库实例
            self.face_database = get_face_database()

            # 初始化FAISS索引，尝试从文件加载，如果不存在则创建新的
            if self.load_index(self.index_path):
                logger.info("faiss_index_loaded_from_file",
                           index_path=self.index_path,
                           total_faces=self.index.ntotal)
            else:
                # 创建新的FAISS索引
                self.index = faiss.IndexFlatL2(self.embedding_dimension)
                logger.info("new_faiss_index_created",
                           embedding_dimension=self.embedding_dimension)

            # 从数据库同步嵌入向量ID（确保数据库和索引的一致性）
            self._sync_database_with_index()

            self.initialized = True
            self.init_time = time.time() - start_time

            logger.info("face_engine_initialized",
                       initialization_time=self.init_time,
                       total_faces=self.index.ntotal)

        except Exception as e:
            logger.error("face_engine_init_failed", error=str(e))
            raise FaceRecognitionException(f"Failed to initialize face engine: {str(e)}")

    def _sync_database_with_index(self):
        """同步数据库和FAISS索引

        确保数据库中的embedding_id与FAISS索引中的ID一致。
        如果索引是从文件加载的，检查是否有数据库记录丢失。
        """
        try:
            if not self.index or self.index.ntotal == 0:
                logger.info("no_faces_in_index_to_sync")
                return

            # 获取数据库中的所有face记录
            faces = self.face_database.get_all_faces(limit=10000)  # 获取所有记录

            if not faces:
                logger.warning("database_empty_but_index_has_faces",
                              index_faces=self.index.ntotal)
                # 可以考虑重建索引，但这里只是记录警告
                return

            # 检查数据库中的embedding_id是否在有效范围内
            max_embedding_id = self.index.ntotal - 1
            invalid_faces = []

            for face in faces:
                embedding_id = face.get("embedding_id")
                if embedding_id is None or embedding_id < 0 or embedding_id > max_embedding_id:
                    invalid_faces.append(face["id"])

            if invalid_faces:
                logger.warning("invalid_embedding_ids_found",
                              count=len(invalid_faces),
                              max_valid_id=max_embedding_id,
                              invalid_face_ids=invalid_faces[:10])  # 只显示前10个

            logger.info("database_index_sync_completed",
                       total_faces_in_index=self.index.ntotal,
                       total_faces_in_database=len(faces),
                       invalid_embedding_ids=len(invalid_faces))

        except Exception as e:
            logger.warning("database_index_sync_failed", error=str(e))

    def is_ready(self) -> bool:
        """检查人脸识别引擎是否已准备好"""
        return self.initialized and self.face_app is not None and self.index is not None

    @cached(namespace="face", ttl=86400, key_params=["image_bytes"])  # 24小时缓存
    def detect_faces(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        检测图像中的人脸

        Args:
            image_bytes: 图像字节数据

        Returns:
            人脸检测结果列表
        """
        if not self.is_ready():
            raise FaceRecognitionException("Face recognition engine is not initialized")

        try:
            # 将字节转换为图像
            img = bytes_to_image(image_bytes)
            if img is None:
                raise FaceDetectionException("Failed to decode image")

            # 检测人脸
            faces = self.face_app.get(img)

            if not faces:
                return []

            # 格式化结果
            formatted_faces = []
            for i, face in enumerate(faces):
                bbox = face.bbox.astype(int)
                landmarks = face.kps.astype(int) if hasattr(face, 'kps') else []

                formatted_faces.append({
                    "face_id": i,
                    "bounding_box": {
                        "x1": int(bbox[0]),
                        "y1": int(bbox[1]),
                        "x2": int(bbox[2]),
                        "y2": int(bbox[3]),
                        "width": int(bbox[2] - bbox[0]),
                        "height": int(bbox[3] - bbox[1]),
                        "area": int((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
                    },
                    "landmarks": landmarks.tolist() if len(landmarks) > 0 else [],
                    "detection_score": float(face.det_score) if hasattr(face, 'det_score') else 0.0,
                    "embedding_available": hasattr(face, 'embedding'),
                    "embedding_dimension": len(face.embedding) if hasattr(face, 'embedding') else 0
                })

            logger.debug("face_detection_completed",
                        face_count=len(formatted_faces),
                        image_size=f"{img.shape[1]}x{img.shape[0]}")

            return formatted_faces

        except Exception as e:
            logger.error("face_detection_failed", error=str(e))
            raise FaceDetectionException(f"Face detection failed: {str(e)}")

    def register_face(self, image_bytes: bytes, name: str,
                     metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        注册新人脸

        Args:
            image_bytes: 包含人脸的图像字节数据
            name: 人名
            metadata: 元数据

        Returns:
            注册结果

        Raises:
            FaceRecognitionException: 如果是只读副本或引擎未就绪
        """
        if not self.is_ready():
            raise FaceRecognitionException("Face recognition engine is not initialized")

        # 检查是否为只读副本
        if self.readonly:
            raise FaceRecognitionException("Cannot register face on read-only replica instance")

        try:
            # 检测人脸
            faces = self.detect_faces(image_bytes)
            if not faces:
                raise FaceDetectionException("No face detected in the image")

            # 使用最大的人脸（通常是最清晰的）
            main_face_idx = self._get_main_face_index(faces)
            if main_face_idx is None:
                raise FaceDetectionException("Could not determine main face")

            # 获取图像和检测到的人脸
            img = bytes_to_image(image_bytes)
            insight_faces = self.face_app.get(img)

            if main_face_idx >= len(insight_faces):
                raise FaceDetectionException("Face index out of range")

            face = insight_faces[main_face_idx]
            if not hasattr(face, 'embedding'):
                raise FaceRecognitionException("Face embedding not available")

            # 提取特征向量
            embedding = face.embedding

            # 添加到FAISS索引
            embedding_np = np.array([embedding], dtype=np.float32)
            faiss.normalize_L2(embedding_np)

            # 添加到索引并获取ID
            self.index.add(embedding_np)
            embedding_id = self.index.ntotal - 1  # 新添加的向量的索引

            # 保存到数据库
            face_id = self.face_database.add_face(name, embedding_id, metadata)

            # 保存FAISS索引到文件
            if self.save_index(self.index_path):
                logger.debug("faiss_index_saved_after_registration",
                           index_path=self.index_path)
            else:
                logger.warning("faiss_index_save_failed_after_registration",
                             index_path=self.index_path)

            logger.info("face_registered_successfully",
                       face_id=face_id,
                       name=name,
                       embedding_id=embedding_id,
                       embedding_dimension=len(embedding))

            return {
                "face_id": face_id,
                "name": name,
                "embedding_id": embedding_id,
                "embedding_dimension": len(embedding),
                "detection_info": faces[main_face_idx],
                "total_faces_registered": self.index.ntotal
            }

        except Exception as e:
            logger.error("face_registration_failed",
                        error=str(e),
                        name=name)
            raise FaceRecognitionException(f"Face registration failed: {str(e)}")

    @cached(namespace="face", ttl=3600, key_params=["image_bytes", "confidence_threshold"])
    def recognize_face(self, image_bytes: bytes,
                      confidence_threshold: Optional[float] = None) -> Dict[str, Any]:
        """
        识别人脸

        Args:
            image_bytes: 包含人脸的图像字节数据
            confidence_threshold: 置信度阈值，如果为None则使用默认值

        Returns:
            识别结果
        """
        if not self.is_ready():
            raise FaceRecognitionException("Face recognition engine is not initialized")

        if self.index.ntotal == 0:
            raise FaceRecognitionException("No faces registered in the system")

        try:
            # 检测人脸
            faces = self.detect_faces(image_bytes)
            if not faces:
                raise FaceDetectionException("No face detected in the image")

            # 使用最大的人脸
            main_face_idx = self._get_main_face_index(faces)
            if main_face_idx is None:
                raise FaceDetectionException("Could not determine main face")

            # 获取图像和检测到的人脸
            img = bytes_to_image(image_bytes)
            insight_faces = self.face_app.get(img)

            if main_face_idx >= len(insight_faces):
                raise FaceDetectionException("Face index out of range")

            face = insight_faces[main_face_idx]
            if not hasattr(face, 'embedding'):
                raise FaceRecognitionException("Face embedding not available")

            # 提取特征向量
            embedding = face.embedding

            # 在FAISS索引中搜索
            embedding_np = np.array([embedding], dtype=np.float32)
            faiss.normalize_L2(embedding_np)

            # 搜索最相似的向量
            k = min(5, self.index.ntotal)  # 搜索前k个最相似的结果
            distances, indices = self.index.search(embedding_np, k)

            # 处理搜索结果
            recognition_threshold = confidence_threshold or self.recognition_threshold
            results = []

            for i in range(k):
                idx = indices[0][i]
                distance = distances[0][i]

                if idx == -1:
                    continue  # 无效索引

                # 转换为相似度分数（1 - 归一化距离）
                similarity = max(0.0, 1.0 - distance / 2.0)  # L2距离转换为相似度

                # 获取对应的人脸记录
                face_record = self.face_database.get_face_by_embedding_id(idx)

                if face_record:
                    results.append({
                        "embedding_id": idx,
                        "distance": float(distance),
                        "similarity": float(similarity),
                        "name": face_record["name"],
                        "face_id": face_record["id"],
                        "metadata": face_record.get("metadata"),
                        "is_match": similarity >= recognition_threshold
                    })

            # 选择最佳匹配
            best_match = None
            if results:
                # 按相似度排序
                results.sort(key=lambda x: x["similarity"], reverse=True)
                best_match = results[0]

                # 检查是否达到阈值
                if best_match["similarity"] < recognition_threshold:
                    best_match = None

            detection_info = faces[main_face_idx]

            logger.debug("face_recognition_completed",
                        best_match=best_match["name"] if best_match else "unknown",
                        similarity=best_match["similarity"] if best_match else 0.0,
                        total_matches=len(results))

            return {
                "detection_info": detection_info,
                "best_match": best_match,
                "all_matches": results,
                "recognition_threshold": recognition_threshold,
                "embedding_dimension": len(embedding)
            }

        except Exception as e:
            logger.error("face_recognition_failed", error=str(e))
            raise FaceRecognitionException(f"Face recognition failed: {str(e)}")

    def recognize_multiple_faces(self, image_bytes: bytes,
                                confidence_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        识别图像中的多个人脸

        Args:
            image_bytes: 图像字节数据
            confidence_threshold: 置信度阈值

        Returns:
            每个人脸的识别结果列表
        """
        if not self.is_ready():
            raise FaceRecognitionException("Face recognition engine is not initialized")

        if self.index.ntotal == 0:
            raise FaceRecognitionException("No faces registered in the system")

        try:
            # 检测所有人脸
            faces = self.detect_faces(image_bytes)
            if not faces:
                return []

            img = bytes_to_image(image_bytes)
            insight_faces = self.face_app.get(img)

            recognition_threshold = confidence_threshold or self.recognition_threshold
            results = []

            for i, (face_info, insight_face) in enumerate(zip(faces, insight_faces)):
                if not hasattr(insight_face, 'embedding'):
                    continue

                # 提取特征向量
                embedding = insight_face.embedding

                # 在FAISS索引中搜索
                embedding_np = np.array([embedding], dtype=np.float32)
                faiss.normalize_L2(embedding_np)

                # 搜索最相似的向量
                k = min(3, self.index.ntotal)
                distances, indices = self.index.search(embedding_np, k)

                # 处理这个脸的识别结果
                face_results = []
                for j in range(k):
                    idx = indices[0][j]
                    distance = distances[0][j]

                    if idx == -1:
                        continue

                    similarity = max(0.0, 1.0 - distance / 2.0)
                    face_record = self.face_database.get_face_by_embedding_id(idx)

                    if face_record:
                        face_results.append({
                            "embedding_id": idx,
                            "distance": float(distance),
                            "similarity": float(similarity),
                            "name": face_record["name"],
                            "face_id": face_record["id"],
                            "is_match": similarity >= recognition_threshold
                        })

                # 选择最佳匹配
                best_match = None
                if face_results:
                    face_results.sort(key=lambda x: x["similarity"], reverse=True)
                    best_match = face_results[0]

                    if best_match["similarity"] < recognition_threshold:
                        best_match = None

                results.append({
                    "face_index": i,
                    "detection_info": face_info,
                    "best_match": best_match,
                    "all_matches": face_results,
                    "embedding_dimension": len(embedding)
                })

            logger.debug("multiple_faces_recognition_completed",
                        face_count=len(results),
                        recognized_count=sum(1 for r in results if r["best_match"]))

            return results

        except Exception as e:
            logger.error("multiple_faces_recognition_failed", error=str(e))
            raise FaceRecognitionException(f"Multiple faces recognition failed: {str(e)}")

    def _get_main_face_index(self, faces: List[Dict[str, Any]]) -> Optional[int]:
        """
        获取主要人脸的索引（最大的人脸）

        Args:
            faces: 人脸检测结果列表

        Returns:
            主要人脸的索引，如果没有检测到人脸则返回None
        """
        if not faces:
            return None

        # 选择面积最大的人脸
        max_area = -1
        main_face_idx = None

        for i, face in enumerate(faces):
            area = face["bounding_box"]["area"]
            if area > max_area:
                max_area = area
                main_face_idx = i

        return main_face_idx

    def get_registered_faces(self) -> List[Dict[str, Any]]:
        """获取所有已注册的人脸信息"""
        try:
            faces = self.face_database.get_all_faces(limit=1000)
            return faces
        except Exception as e:
            logger.error("get_registered_faces_failed", error=str(e))
            return []

    def delete_face(self, face_id: int) -> bool:
        """
        删除已注册的人脸

        Args:
            face_id: 人脸ID

        Returns:
            是否成功删除

        Raises:
            FaceRecognitionException: 如果是只读副本
        """
        # 检查是否为只读副本
        if self.readonly:
            raise FaceRecognitionException("Cannot delete face on read-only replica instance")

        try:
            # 从数据库获取人脸记录
            face_record = self.face_database.get_face(face_id)
            if not face_record:
                return False

            # 从数据库删除
            deleted = self.face_database.delete_face(face_id)

            if deleted:
                # 注意：FAISS索引不支持删除操作
                # 在实际应用中，需要实现索引的持久化和重建
                logger.warning("face_deleted_from_database_but_not_from_faiss",
                             face_id=face_id,
                             embedding_id=face_record["embedding_id"])

            return deleted

        except Exception as e:
            logger.error("delete_face_failed", error=str(e), face_id=face_id)
            return False

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "model_name": self.model_name,
            "initialized": self.initialized,
            "initialization_time": self.init_time,
            "total_registered_faces": self.index.ntotal if self.index else 0,
            "embedding_dimension": self.embedding_dimension,
            "recognition_threshold": self.recognition_threshold,
            "database_connected": self.face_database is not None
        }

    def save_index(self, index_path: str) -> bool:
        """
        保存FAISS索引到文件

        Args:
            index_path: 索引文件路径

        Returns:
            是否成功保存
        """
        try:
            if not self.index:
                return False

            faiss.write_index(self.index, index_path)
            logger.info("faiss_index_saved", index_path=index_path)
            return True

        except Exception as e:
            logger.error("save_index_failed", error=str(e), index_path=index_path)
            return False

    def load_index(self, index_path: str) -> bool:
        """
        从文件加载FAISS索引

        Args:
            index_path: 索引文件路径

        Returns:
            是否成功加载
        """
        try:
            if not os.path.exists(index_path):
                logger.warning("index_file_not_found", index_path=index_path)
                return False

            self.index = faiss.read_index(index_path)
            logger.info("faiss_index_loaded",
                       index_path=index_path,
                       total_faces=self.index.ntotal)
            return True

        except Exception as e:
            logger.error("load_index_failed", error=str(e), index_path=index_path)
            return False


# 全局人脸识别引擎实例
_face_engine = None


def get_face_engine() -> FaceRecognitionEngine:
    """获取全局人脸识别引擎实例"""
    global _face_engine
    if _face_engine is None:
        _face_engine = FaceRecognitionEngine(instance_role=config.instance_role)
    return _face_engine