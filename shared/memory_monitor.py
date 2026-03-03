"""
内存监控模块
监控和管理服务的内存使用
"""

import os
import psutil
import time
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from shared.utils import logger


class MemoryState(Enum):
    """内存状态枚举"""
    NORMAL = "normal"       # 内存使用正常
    WARNING = "warning"     # 内存使用警告
    CRITICAL = "critical"   # 内存使用严重
    LIMIT_EXCEEDED = "limit_exceeded"  # 超过内存限制


@dataclass
class MemoryStats:
    """内存统计信息"""
    total_bytes: int
    available_bytes: int
    used_bytes: int
    used_percent: float
    process_rss_bytes: int  # 进程常驻内存大小
    process_vms_bytes: int  # 进程虚拟内存大小
    process_memory_percent: float


class MemoryMonitor:
    """内存监控器"""

    def __init__(
        self,
        warning_threshold_percent: float = 75.0,
        critical_threshold_percent: float = 85.0,
        process_memory_limit_mb: Optional[float] = None,
        check_interval_seconds: int = 30
    ):
        """
        初始化内存监控器

        Args:
            warning_threshold_percent: 系统内存警告阈值百分比
            critical_threshold_percent: 系统内存严重阈值百分比
            process_memory_limit_mb: 进程内存限制（MB），如果为None则不限制
            check_interval_seconds: 检查间隔（秒）
        """
        self.warning_threshold = warning_threshold_percent
        self.critical_threshold = critical_threshold_percent
        self.process_memory_limit_bytes = (
            process_memory_limit_mb * 1024 * 1024
            if process_memory_limit_mb is not None
            else None
        )
        self.check_interval = check_interval_seconds
        self._stop_event = threading.Event()
        self._monitor_thread = None
        self._last_stats: Optional[MemoryStats] = None
        self._current_state = MemoryState.NORMAL
        self._state_history = []
        self._callbacks = {
            MemoryState.WARNING: [],
            MemoryState.CRITICAL: [],
            MemoryState.LIMIT_EXCEEDED: []
        }

    def get_memory_stats(self) -> MemoryStats:
        """获取当前内存统计信息"""
        # 获取系统内存信息
        system_memory = psutil.virtual_memory()

        # 获取进程内存信息
        process = psutil.Process(os.getpid())
        process_memory_info = process.memory_info()

        # 计算进程内存使用百分比
        process_memory_percent = process.memory_percent()

        return MemoryStats(
            total_bytes=system_memory.total,
            available_bytes=system_memory.available,
            used_bytes=system_memory.used,
            used_percent=system_memory.percent,
            process_rss_bytes=process_memory_info.rss,
            process_vms_bytes=process_memory_info.vms,
            process_memory_percent=process_memory_percent
        )

    def check_memory_state(self) -> MemoryState:
        """
        检查内存状态

        Returns:
            当前内存状态
        """
        stats = self.get_memory_stats()
        self._last_stats = stats

        # 检查进程内存限制
        if (self.process_memory_limit_bytes is not None and
            stats.process_rss_bytes > self.process_memory_limit_bytes):
            return MemoryState.LIMIT_EXCEEDED

        # 检查系统内存使用
        if stats.used_percent >= self.critical_threshold:
            return MemoryState.CRITICAL
        elif stats.used_percent >= self.warning_threshold:
            return MemoryState.WARNING
        else:
            return MemoryState.NORMAL

    def add_state_callback(self, state: MemoryState, callback):
        """
        添加状态回调函数

        Args:
            state: 内存状态
            callback: 回调函数，当状态变化到指定状态时调用
        """
        if state in self._callbacks:
            self._callbacks[state].append(callback)
        else:
            raise ValueError(f"Invalid state: {state}. Must be one of {list(self._callbacks.keys())}")

    def _monitor_loop(self):
        """监控循环"""
        logger.info("memory_monitor_started",
                   warning_threshold=self.warning_threshold,
                   critical_threshold=self.critical_threshold,
                   process_memory_limit_mb=(
                       self.process_memory_limit_bytes / (1024 * 1024)
                       if self.process_memory_limit_bytes
                       else None
                   ),
                   check_interval=self.check_interval)

        while not self._stop_event.is_set():
            try:
                old_state = self._current_state
                self._current_state = self.check_memory_state()

                # 记录状态变化
                if old_state != self._current_state:
                    self._state_history.append({
                        "timestamp": time.time(),
                        "old_state": old_state.value,
                        "new_state": self._current_state.value,
                        "stats": self._last_stats.__dict__ if self._last_stats else None
                    })

                    logger.info("memory_state_changed",
                               old_state=old_state.value,
                               new_state=self._current_state.value,
                               stats=self._last_stats.__dict__ if self._last_stats else None)

                    # 触发回调
                    if self._current_state in self._callbacks:
                        for callback in self._callbacks[self._current_state]:
                            try:
                                callback(self._current_state, self._last_stats)
                            except Exception as e:
                                logger.error("memory_callback_failed",
                                           callback=str(callback),
                                           error=str(e))

                # 记录周期性状态（仅在状态不是NORMAL时）
                if self._current_state != MemoryState.NORMAL:
                    logger.warning("memory_state_periodic_check",
                                  state=self._current_state.value,
                                  stats=self._last_stats.__dict__ if self._last_stats else None)

            except Exception as e:
                logger.error("memory_monitor_error", error=str(e))

            # 等待下一次检查
            self._stop_event.wait(self.check_interval)

    def start(self):
        """启动内存监控"""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            logger.warning("memory_monitor_already_running")
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="MemoryMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("memory_monitor_thread_started")

    def stop(self):
        """停止内存监控"""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None
        logger.info("memory_monitor_stopped")

    def get_status(self) -> Dict[str, Any]:
        """获取监控器状态"""
        stats = self.get_memory_stats() if self._last_stats is None else self._last_stats

        return {
            "monitoring": self._monitor_thread is not None and self._monitor_thread.is_alive(),
            "current_state": self._current_state.value,
            "stats": {
                "system_memory": {
                    "total_mb": round(stats.total_bytes / (1024 * 1024), 2),
                    "available_mb": round(stats.available_bytes / (1024 * 1024), 2),
                    "used_mb": round(stats.used_bytes / (1024 * 1024), 2),
                    "used_percent": round(stats.used_percent, 2)
                },
                "process_memory": {
                    "rss_mb": round(stats.process_rss_bytes / (1024 * 1024), 2),
                    "vms_mb": round(stats.process_vms_bytes / (1024 * 1024), 2),
                    "percent": round(stats.process_memory_percent, 2)
                }
            },
            "thresholds": {
                "warning": self.warning_threshold,
                "critical": self.critical_threshold,
                "process_limit_mb": (
                    self.process_memory_limit_bytes / (1024 * 1024)
                    if self.process_memory_limit_bytes
                    else None
                )
            },
            "state_history_count": len(self._state_history)
        }

    def clear_cache_on_critical(self):
        """在内存严重时清除缓存（回调函数示例）"""
        def callback(state: MemoryState, stats: MemoryStats):
            if state == MemoryState.CRITICAL:
                logger.warning("clearing_cache_due_to_critical_memory",
                              used_percent=stats.used_percent,
                              process_rss_mb=stats.process_rss_bytes / (1024 * 1024))

                # 这里可以添加清除缓存的逻辑
                # 例如：get_cache().clear_namespace("face")
                # 例如：get_cache().clear_namespace("ocr")

        return callback

    def reduce_processing_on_warning(self):
        """在内存警告时减少处理（回调函数示例）"""
        def callback(state: MemoryState, stats: MemoryStats):
            if state == MemoryState.WARNING:
                logger.warning("reducing_processing_due_to_memory_warning",
                              used_percent=stats.used_percent)
                # 这里可以添加减少处理的逻辑
                # 例如：限制并发请求数，减少批处理大小等

        return callback


# 全局内存监控器实例
_memory_monitor_instance = None


def get_memory_monitor(
    warning_threshold_percent: float = 75.0,
    critical_threshold_percent: float = 85.0,
    process_memory_limit_mb: Optional[float] = None,
    check_interval_seconds: int = 30
) -> MemoryMonitor:
    """获取全局内存监控器实例"""
    global _memory_monitor_instance
    if _memory_monitor_instance is None:
        _memory_monitor_instance = MemoryMonitor(
            warning_threshold_percent=warning_threshold_percent,
            critical_threshold_percent=critical_threshold_percent,
            process_memory_limit_mb=process_memory_limit_mb,
            check_interval_seconds=check_interval_seconds
        )

    # 添加默认回调
    if not _memory_monitor_instance._callbacks[MemoryState.CRITICAL]:
        _memory_monitor_instance.add_state_callback(
            MemoryState.CRITICAL,
            _memory_monitor_instance.clear_cache_on_critical()
        )

    if not _memory_monitor_instance._callbacks[MemoryState.WARNING]:
        _memory_monitor_instance.add_state_callback(
            MemoryState.WARNING,
            _memory_monitor_instance.reduce_processing_on_warning()
        )

    return _memory_monitor_instance


def start_memory_monitoring(**kwargs):
    """启动内存监控"""
    monitor = get_memory_monitor(**kwargs)
    monitor.start()
    return monitor


def get_memory_status() -> Dict[str, Any]:
    """获取内存状态"""
    monitor = get_memory_monitor()
    return monitor.get_status()