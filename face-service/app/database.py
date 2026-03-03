"""
人脸识别服务数据库模块
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from contextlib import contextmanager

from shared.config import config
from shared.utils import logger, ensure_directory_exists
from shared.exceptions import DatabaseException


class FaceDatabase:
    """人脸数据库管理"""

    def __init__(self, db_path: Optional[str] = None, instance_role: str = "primary"):
        """
        初始化人脸数据库

        Args:
            db_path: 数据库文件路径，如果为None则使用配置中的路径
            instance_role: 实例角色，'primary'（主实例，可读写）或 'replica'（副本，只读）
        """
        if db_path is None:
            # 从数据库URL中提取路径
            db_url = config.database_url
            if db_url.startswith("sqlite:///"):
                db_path = db_url.replace("sqlite:///", "")
            else:
                db_path = "./data/faces.db"

        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir:
            ensure_directory_exists(db_dir)

        self.db_path = db_path
        self.instance_role = instance_role  # 'primary' 或 'replica'
        self.readonly = (instance_role == "replica")
        self._initialize_database()

    def _initialize_database(self):
        """初始化数据库表

        注意：只读副本跳过表创建
        """
        if self.readonly:
            logger.info("face_database_skip_init_for_replica", db_path=self.db_path)
            return

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 创建人脸表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS faces (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        embedding_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT,
                        UNIQUE(name, embedding_id)
                    )
                """)

                # 创建索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_name ON faces(name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_embedding_id ON faces(embedding_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_created_at ON faces(created_at)")

                conn.commit()
                logger.info("face_database_initialized", db_path=self.db_path)

        except Exception as e:
            logger.error("face_database_init_failed", error=str(e))
            raise DatabaseException("initialize_database", str(e))

    @contextmanager
    def _get_connection(self):
        """获取数据库连接（上下文管理器）

        支持WAL模式和多进程访问：
        - 主实例：读写模式，启用WAL模式
        - 副本实例：只读模式
        """
        conn = None
        try:
            # 根据实例角色设置连接模式
            if self.readonly:
                # 只读副本：使用只读模式连接
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                logger.debug("database_connection_opened_readonly", db_path=self.db_path)
            else:
                # 主实例：读写模式，启用WAL模式
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row

                # 启用WAL模式支持多进程访问
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA wal_autocheckpoint=1000")
                conn.execute("PRAGMA busy_timeout=5000")  # 5秒超时

                # 设置连接限制
                conn.execute("PRAGMA max_page_count=2147483646")  # 最大页数

                logger.debug("database_connection_opened_readwrite", db_path=self.db_path)

            yield conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and not self.readonly:
                logger.warning("database_locked_retry", error=str(e))
                # 可以在这里添加重试逻辑
                raise DatabaseException("get_connection", f"Database locked: {str(e)}")
            else:
                logger.error("database_connection_failed", error=str(e), readonly=self.readonly)
                raise DatabaseException("get_connection", str(e))
        except Exception as e:
            logger.error("database_connection_failed", error=str(e), readonly=self.readonly)
            raise DatabaseException("get_connection", str(e))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass  # 忽略关闭异常

    def add_face(self, name: str, embedding_id: int, metadata: Optional[Dict] = None) -> int:
        """
        添加人脸记录

        Args:
            name: 人名
            embedding_id: 嵌入向量ID（对应FAISS索引中的ID）
            metadata: 元数据

        Returns:
            插入的记录ID

        Raises:
            DatabaseException: 如果是只读副本或数据库错误
        """
        # 检查是否为只读副本
        if self.readonly:
            logger.error("add_face_attempted_on_replica",
                        name=name,
                        embedding_id=embedding_id)
            raise DatabaseException("add_face", "Cannot add face on read-only replica instance")

        try:
            metadata_str = None
            if metadata:
                import json
                metadata_str = json.dumps(metadata)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO faces (name, embedding_id, metadata, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (name, embedding_id, metadata_str))

                face_id = cursor.lastrowid
                conn.commit()

                logger.info("face_record_added",
                           face_id=face_id,
                           name=name,
                           embedding_id=embedding_id)

                return face_id

        except Exception as e:
            logger.error("add_face_failed", error=str(e), name=name, embedding_id=embedding_id)
            raise DatabaseException("add_face", str(e))

    def get_face(self, face_id: int) -> Optional[Dict[str, Any]]:
        """
        获取人脸记录

        Args:
            face_id: 人脸ID

        Returns:
            人脸记录字典，如果不存在则返回None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM faces WHERE id = ?", (face_id,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_dict(row)
                return None

        except Exception as e:
            logger.error("get_face_failed", error=str(e), face_id=face_id)
            raise DatabaseException("get_face", str(e))

    def get_face_by_embedding_id(self, embedding_id: int) -> Optional[Dict[str, Any]]:
        """
        通过嵌入向量ID获取人脸记录

        Args:
            embedding_id: 嵌入向量ID

        Returns:
            人脸记录字典
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM faces WHERE embedding_id = ?", (embedding_id,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_dict(row)
                return None

        except Exception as e:
            logger.error("get_face_by_embedding_id_failed",
                        error=str(e),
                        embedding_id=embedding_id)
            raise DatabaseException("get_face_by_embedding_id", str(e))

    def get_faces_by_name(self, name: str) -> List[Dict[str, Any]]:
        """
        通过人名获取人脸记录列表

        Args:
            name: 人名

        Returns:
            人脸记录列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM faces WHERE name = ? ORDER BY created_at DESC", (name,))
                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error("get_faces_by_name_failed", error=str(e), name=name)
            raise DatabaseException("get_faces_by_name", str(e))

    def get_all_faces(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取所有人脸记录

        Args:
            limit: 限制数量
            offset: 偏移量

        Returns:
            人脸记录列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM faces
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error("get_all_faces_failed", error=str(e))
            raise DatabaseException("get_all_faces", str(e))

    def update_face(self, face_id: int, name: Optional[str] = None,
                   metadata: Optional[Dict] = None) -> bool:
        """
        更新人脸记录

        Args:
            face_id: 人脸ID
            name: 新的人名（如果提供）
            metadata: 新的元数据（如果提供）

        Returns:
            是否成功更新

        Raises:
            DatabaseException: 如果是只读副本
        """
        # 检查是否为只读副本
        if self.readonly:
            logger.error("update_face_attempted_on_replica", face_id=face_id)
            raise DatabaseException("update_face", "Cannot update face on read-only replica instance")

        try:
            update_fields = []
            params = []

            if name is not None:
                update_fields.append("name = ?")
                params.append(name)

            if metadata is not None:
                import json
                metadata_str = json.dumps(metadata)
                update_fields.append("metadata = ?")
                params.append(metadata_str)

            if not update_fields:
                return False  # 没有需要更新的字段

            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(face_id)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                sql = f"""
                    UPDATE faces
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                cursor.execute(sql, params)

                updated = cursor.rowcount > 0
                conn.commit()

                if updated:
                    logger.info("face_record_updated",
                               face_id=face_id,
                               updated_fields=update_fields)

                return updated

        except Exception as e:
            logger.error("update_face_failed", error=str(e), face_id=face_id)
            raise DatabaseException("update_face", str(e))

    def delete_face(self, face_id: int) -> bool:
        """
        删除人脸记录

        Args:
            face_id: 人脸ID

        Returns:
            是否成功删除

        Raises:
            DatabaseException: 如果是只读副本
        """
        # 检查是否为只读副本
        if self.readonly:
            logger.error("delete_face_attempted_on_replica", face_id=face_id)
            raise DatabaseException("delete_face", "Cannot delete face on read-only replica instance")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM faces WHERE id = ?", (face_id,))

                deleted = cursor.rowcount > 0
                conn.commit()

                if deleted:
                    logger.info("face_record_deleted", face_id=face_id)

                return deleted

        except Exception as e:
            logger.error("delete_face_failed", error=str(e), face_id=face_id)
            raise DatabaseException("delete_face", str(e))

    def delete_faces_by_name(self, name: str) -> int:
        """
        删除指定名字的所有人脸记录

        Args:
            name: 人名

        Returns:
            删除的记录数量

        Raises:
            DatabaseException: 如果是只读副本
        """
        # 检查是否为只读副本
        if self.readonly:
            logger.error("delete_faces_by_name_attempted_on_replica", name=name)
            raise DatabaseException("delete_faces_by_name", "Cannot delete faces on read-only replica instance")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM faces WHERE name = ?", (name,))

                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info("faces_deleted_by_name",
                               name=name,
                               count=deleted_count)

                return deleted_count

        except Exception as e:
            logger.error("delete_faces_by_name_failed", error=str(e), name=name)
            raise DatabaseException("delete_faces_by_name", str(e))

    def search_faces(self, name_pattern: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索人脸记录

        Args:
            name_pattern: 名字模式（支持%通配符）
            limit: 限制数量

        Returns:
            人脸记录列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM faces
                    WHERE name LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (name_pattern, limit))
                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error("search_faces_failed", error=str(e), name_pattern=name_pattern)
            raise DatabaseException("search_faces", str(e))

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 总记录数
                cursor.execute("SELECT COUNT(*) as total FROM faces")
                total = cursor.fetchone()[0]

                # 不同人名数量
                cursor.execute("SELECT COUNT(DISTINCT name) as unique_names FROM faces")
                unique_names = cursor.fetchone()[0]

                # 最近创建时间
                cursor.execute("SELECT MAX(created_at) as latest FROM faces")
                latest = cursor.fetchone()[0]

                return {
                    "total_faces": total,
                    "unique_names": unique_names,
                    "latest_creation": latest,
                    "database_path": self.db_path,
                    "database_size": os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                }

        except Exception as e:
            logger.error("get_statistics_failed", error=str(e))
            raise DatabaseException("get_statistics", str(e))

    def backup_database(self, backup_dir: Optional[str] = None) -> str:
        """
        备份数据库

        Args:
            backup_dir: 备份目录，如果为None则使用默认备份目录

        Returns:
            备份文件路径
        """
        try:
            if backup_dir is None:
                backup_dir = "./backups"

            ensure_directory_exists(backup_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"faces_backup_{timestamp}.db")

            import shutil
            shutil.copy2(self.db_path, backup_path)

            logger.info("database_backup_created",
                       backup_path=backup_path,
                       original_size=os.path.getsize(self.db_path))

            return backup_path

        except Exception as e:
            logger.error("database_backup_failed", error=str(e))
            raise DatabaseException("backup_database", str(e))

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        result = {}
        for key in row.keys():
            value = row[key]

            # 解析JSON元数据
            if key == "metadata" and value:
                try:
                    import json
                    value = json.loads(value)
                except:
                    pass

            result[key] = value

        return result


# 全局数据库实例
_face_database = None


def get_face_database() -> FaceDatabase:
    """获取全局人脸数据库实例"""
    global _face_database
    if _face_database is None:
        _face_database = FaceDatabase(instance_role=config.instance_role)
    return _face_database