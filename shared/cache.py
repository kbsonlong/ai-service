"""
共享缓存模块
为AI微服务提供统一的缓存功能
"""

import json
import hashlib
import time
from typing import Any, Optional, Union, Dict, List
from functools import wraps

import redis
from shared.config import config
from shared.utils import logger


class CacheError(Exception):
    """缓存错误"""
    pass


class RedisCache:
    """Redis缓存客户端"""

    def __init__(self, redis_url: Optional[str] = None, prefix: str = "ai:cache:"):
        """
        初始化Redis缓存

        Args:
            redis_url: Redis连接URL，如果为None则使用配置中的URL
            prefix: 缓存键前缀
        """
        self.redis_url = redis_url or config.redis_url
        self.prefix = prefix
        self._client = None
        self._connected = False

    @property
    def client(self) -> redis.Redis:
        """获取Redis客户端（懒加载）"""
        if self._client is None:
            try:
                self._client = redis.from_url(self.redis_url, decode_responses=True)
                # 测试连接
                self._client.ping()
                self._connected = True
                logger.info("redis_cache_connected", redis_url=self.redis_url)
            except Exception as e:
                logger.error("redis_cache_connection_failed",
                            redis_url=self.redis_url, error=str(e))
                raise CacheError(f"Failed to connect to Redis: {str(e)}")
        return self._client

    def is_connected(self) -> bool:
        """检查是否连接到Redis"""
        if not self._connected:
            try:
                self.client.ping()
                self._connected = True
            except:
                self._connected = False
        return self._connected

    def generate_key(self, namespace: str, *args, **kwargs) -> str:
        """
        生成缓存键

        Args:
            namespace: 命名空间（如：face、ocr、video）
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            缓存键
        """
        # 创建键的字符串表示
        key_parts = [namespace]

        # 添加位置参数
        for arg in args:
            key_parts.append(str(arg))

        # 添加关键字参数（排序以确保一致性）
        for key in sorted(kwargs.keys()):
            key_parts.append(f"{key}={kwargs[key]}")

        # 合并并哈希
        key_str = ":".join(key_parts)
        if len(key_str) > 100:  # 如果键太长，使用哈希
            key_str = hashlib.md5(key_str.encode()).hexdigest()

        return f"{self.prefix}{key_str}"

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值（可以是任意JSON可序列化的对象）
            ttl: 过期时间（秒），如果为None则永不过期

        Returns:
            是否成功设置
        """
        if not self.is_connected():
            return False

        try:
            # 序列化值
            value_json = json.dumps(value)

            if ttl is not None:
                result = self.client.setex(key, ttl, value_json)
            else:
                result = self.client.set(key, value_json)

            return result is True
        except Exception as e:
            logger.error("cache_set_failed", key=key, error=str(e))
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值

        Args:
            key: 缓存键
            default: 默认值（如果缓存未命中或出错）

        Returns:
            缓存值或默认值
        """
        if not self.is_connected():
            return default

        try:
            value_json = self.client.get(key)
            if value_json is None:
                return default

            return json.loads(value_json)
        except Exception as e:
            logger.error("cache_get_failed", key=key, error=str(e))
            return default

    def delete(self, key: str) -> bool:
        """删除缓存键"""
        if not self.is_connected():
            return False

        try:
            result = self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error("cache_delete_failed", key=key, error=str(e))
            return False

    def exists(self, key: str) -> bool:
        """检查缓存键是否存在"""
        if not self.is_connected():
            return False

        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error("cache_exists_failed", key=key, error=str(e))
            return False

    def clear_namespace(self, namespace: str) -> int:
        """
        清除指定命名空间的所有缓存

        Args:
            namespace: 命名空间

        Returns:
            删除的键数量
        """
        if not self.is_connected():
            return 0

        try:
            pattern = f"{self.prefix}{namespace}:*"
            keys = self.client.keys(pattern)

            if keys:
                deleted = self.client.delete(*keys)
                logger.info("cache_namespace_cleared",
                          namespace=namespace, deleted_count=deleted)
                return deleted
            return 0
        except Exception as e:
            logger.error("cache_clear_namespace_failed",
                        namespace=namespace, error=str(e))
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.is_connected():
            return {"connected": False}

        try:
            info = self.client.info()
            stats = {
                "connected": True,
                "keys": self.client.dbsize(),
                "memory_used": info.get("used_memory", 0),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "uptime": info.get("uptime_in_seconds", 0),
            }

            # 计算命中率
            total = stats["hits"] + stats["misses"]
            if total > 0:
                stats["hit_rate"] = stats["hits"] / total
            else:
                stats["hit_rate"] = 0.0

            return stats
        except Exception as e:
            logger.error("cache_stats_failed", error=str(e))
            return {"connected": False, "error": str(e)}


def cached(namespace: str, ttl: int = 3600, key_params: Optional[List[str]] = None):
    """
    缓存装饰器

    Args:
        namespace: 缓存命名空间
        ttl: 缓存时间（秒）
        key_params: 用于生成缓存键的参数名列表，如果为None则使用所有参数

    Example:
        @cached(namespace="face", ttl=3600, key_params=["image_bytes"])
        def recognize_face(image_bytes: bytes, threshold: float = 0.6):
            # 函数实现
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取缓存实例
            cache = get_cache()
            if not cache.is_connected():
                # 如果缓存不可用，直接执行函数
                return func(*args, **kwargs)

            # 确定要用于生成缓存键的参数
            func_params = list(func.__code__.co_varnames[:func.__code__.co_argcount])

            # 如果指定了key_params，只使用这些参数
            if key_params:
                used_params = {}
                for i, param_name in enumerate(func_params):
                    if i < len(args) and param_name in key_params:
                        used_params[param_name] = args[i]

                for param_name in key_params:
                    if param_name in kwargs:
                        used_params[param_name] = kwargs[param_name]
            else:
                # 使用所有参数
                used_params = {}
                for i, param_name in enumerate(func_params):
                    if i < len(args):
                        used_params[param_name] = args[i]

                used_params.update(kwargs)

            # 生成缓存键
            cache_key = cache.generate_key(namespace, func.__name__, **used_params)

            # 尝试从缓存获取
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug("cache_hit",
                           function=func.__name__,
                           namespace=namespace,
                           key=cache_key)
                return cached_result["result"]

            # 缓存未命中，执行函数
            logger.debug("cache_miss",
                       function=func.__name__,
                       namespace=namespace,
                       key=cache_key)

            result = func(*args, **kwargs)

            # 将结果存入缓存
            cache_value = {
                "result": result,
                "timestamp": time.time(),
                "function": func.__name__,
                "namespace": namespace
            }
            cache.set(cache_key, cache_value, ttl)

            return result

        return wrapper
    return decorator


# 全局缓存实例
_cache_instance = None


def get_cache() -> RedisCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache()
    return _cache_instance


def clear_cache() -> bool:
    """清除所有缓存"""
    cache = get_cache()
    if not cache.is_connected():
        return False

    try:
        cache.client.flushdb()
        logger.info("cache_cleared")
        return True
    except Exception as e:
        logger.error("clear_cache_failed", error=str(e))
        return False