"""System metrics collection for the dashboard."""

from __future__ import annotations

import platform
import sys
from ctypes import Structure, byref, c_ulong, c_ulonglong, sizeof
from dataclasses import dataclass
from datetime import datetime

from iris import __version__


@dataclass(frozen=True)
class SystemMetrics:
    """Current system and application metrics."""

    cpu_percent: float
    ram_percent: float
    python_version: str
    current_time: str
    iris_version: str


class MetricsService:
    """Collect lightweight runtime metrics."""

    def __init__(self) -> None:
        self._last_idle: int | None = None
        self._last_total: int | None = None

    def snapshot(self) -> SystemMetrics:
        """Return the latest system metrics snapshot."""
        return SystemMetrics(
            cpu_percent=self._cpu_percent(),
            ram_percent=self._ram_percent(),
            python_version=platform.python_version(),
            current_time=datetime.now().strftime("%H:%M:%S"),
            iris_version=__version__,
        )

    def _cpu_percent(self) -> float:
        if sys.platform != "win32":
            return 0.0

        idle_time = _FileTime()
        kernel_time = _FileTime()
        user_time = _FileTime()
        if not getattr(__import__("ctypes"), "windll").kernel32.GetSystemTimes(
            byref(idle_time),
            byref(kernel_time),
            byref(user_time),
        ):
            return 0.0

        idle = idle_time.to_int()
        total = kernel_time.to_int() + user_time.to_int()
        if self._last_idle is None or self._last_total is None:
            self._last_idle = idle
            self._last_total = total
            return 0.0

        idle_delta = idle - self._last_idle
        total_delta = total - self._last_total
        self._last_idle = idle
        self._last_total = total

        if total_delta <= 0:
            return 0.0

        return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))

    def _ram_percent(self) -> float:
        if sys.platform != "win32":
            return 0.0

        memory_status = _MemoryStatusEx()
        memory_status.dwLength = sizeof(_MemoryStatusEx)
        if not getattr(__import__("ctypes"), "windll").kernel32.GlobalMemoryStatusEx(
            byref(memory_status)
        ):
            return 0.0

        return float(memory_status.dwMemoryLoad)


class _FileTime(Structure):
    """Windows FILETIME structure."""

    _fields_ = [
        ("dwLowDateTime", c_ulong),
        ("dwHighDateTime", c_ulong),
    ]

    def to_int(self) -> int:
        """Return the file time as a single integer."""
        return (self.dwHighDateTime << 32) + self.dwLowDateTime


class _MemoryStatusEx(Structure):
    """Windows MEMORYSTATUSEX structure."""

    _fields_ = [
        ("dwLength", c_ulong),
        ("dwMemoryLoad", c_ulong),
        ("ullTotalPhys", c_ulonglong),
        ("ullAvailPhys", c_ulonglong),
        ("ullTotalPageFile", c_ulonglong),
        ("ullAvailPageFile", c_ulonglong),
        ("ullTotalVirtual", c_ulonglong),
        ("ullAvailVirtual", c_ulonglong),
        ("ullAvailExtendedVirtual", c_ulonglong),
    ]
