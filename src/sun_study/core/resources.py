"""How long a stage took and how much memory the run has needed.

The two numbers a failed run on a larger model is read by. A shadow run that
dies on a big project dies one of three ways -- Archicad's export takes longer
than a command is allowed, the caster asks for more memory than the machine
has, or Archicad refuses something it is asked to draw -- and each wants a
different fix (roadmap R1). A log that says stage by stage how long each step
took and how much memory the process had reached by then tells the three
apart without anybody having watched it happen: the last stage named is the
one that was running, and a peak climbing towards the machine's memory is
the caster.

Standard library only, and nothing of this package's, so the caster in
``core`` can use it as readily as the command line. Every reading answers
``None`` rather than raising where the platform will not say: a figure in a
log is worth having and never worth a failed run.
"""

from __future__ import annotations

import os
import sys
import time

__all__ = [
    "Stopwatch",
    "duration_text",
    "peak_memory_bytes",
    "physical_memory_bytes",
    "size_text",
]


def peak_memory_bytes() -> int | None:
    """The most memory this process has held at once, in bytes.

    The peak rather than the current figure, because the stage that needed
    the memory has usually handed it back by the time its line is printed,
    and "how close did it come" is the question. The working set on Windows,
    the resident set elsewhere.
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            # The K32 form is kernel32's own export of psapi's call, there
            # since Windows 7, so nothing else has to be loaded for it.
            ask = kernel32.K32GetProcessMemoryInfo
            ask.restype = wintypes.BOOL
            ask.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            if not ask(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return None
            return int(counters.PeakWorkingSetSize)
        except (AttributeError, OSError):
            return None
    else:
        try:
            import resource
        except ImportError:  # pragma: no cover - a platform with neither
            return None
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Kilobytes on Linux, bytes on a Mac: the one field the two disagree on.
        return int(peak) if sys.platform == "darwin" else int(peak) * 1024


def physical_memory_bytes() -> int | None:
    """How much memory the machine has, in bytes, for the head of a log."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _Status(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        try:
            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            ask = ctypes.windll.kernel32.GlobalMemoryStatusEx
            ask.restype = wintypes.BOOL
            ask.argtypes = [ctypes.POINTER(_Status)]
            if not ask(ctypes.byref(status)):
                return None
            return int(status.ullTotalPhys)
        except (AttributeError, OSError):
            return None
    else:
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            size = os.sysconf("SC_PAGE_SIZE")
        except (AttributeError, ValueError, OSError):
            return None
        return int(pages) * int(size) if pages > 0 and size > 0 else None


def size_text(count: float | None) -> str:
    """``245 MB``, ``2.1 GB``: a byte count as a person reads one."""
    if count is None:
        return "unknown"
    for unit, scale in (("GB", 1024.0**3), ("MB", 1024.0**2), ("kB", 1024.0)):
        if count >= scale:
            value = count / scale
            return f"{value:.1f} {unit}" if value < 10 else f"{value:,.0f} {unit}"
    return f"{count:.0f} bytes"


def duration_text(seconds: float) -> str:
    """``0.4 s``, ``41 s``, ``3 min 12 s``, ``1 h 04 min``."""
    if seconds < 10:
        return f"{seconds:.1f} s"
    whole = round(seconds)
    if whole < 60:
        return f"{whole} s"
    minutes, rest = divmod(whole, 60)
    if minutes < 60:
        return f"{minutes} min {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


class Stopwatch:
    """The time since the last stage, and since the start, for a log line."""

    def __init__(self) -> None:
        self._start = self._last = time.monotonic()

    def lap(self) -> float:
        """Seconds since the last lap, and start the next."""
        now = time.monotonic()
        took, self._last = now - self._last, now
        return took

    @property
    def total(self) -> float:
        return time.monotonic() - self._start

    def said(self, what: str) -> str:
        """``  timing: read the model in 41 s, memory at most 1.2 GB``.

        One shape for every stage, so a log can be read down the left edge
        for where the time went, and searched for ``timing:`` for the lot.
        """
        took = duration_text(self.lap())
        return f"  timing: {what} in {took}, memory at most {size_text(peak_memory_bytes())}"
