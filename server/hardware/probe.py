"""What is actually in this machine. Missing fields are reported missing, never invented."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from server.models.hardware import GpuInfo, HardwareReport, HostInfo

WSL_NVML_HINT = (
    "Running under WSL2: NVML often withholds power draw and temperature through the passthrough. "
    "Those HUD fields show a dash rather than a guess."
)
WSL_MOUNT_HINT = (
    "Indexing a Windows drive (/mnt/c/...) needs polling - inotify does not fire there. Folders on "
    "the WSL ext4 side are watched natively and cost far less CPU."
)


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def probe_gpus() -> tuple[list[GpuInfo], bool]:
    """Returns (gpus, nvml_available). Never raises: a machine with no NVIDIA GPU is valid."""
    try:
        import pynvml
    except ImportError:
        return [], False
    try:
        pynvml.nvmlInit()
    except Exception:  # noqa: BLE001 - no driver, no NVML, CPU-only box
        return [], False
    gpus: list[GpuInfo] = []
    try:
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            gpus.append(_read_device(pynvml, handle, index))
    finally:
        with _suppress():
            pynvml.nvmlShutdown()
    return gpus, True


def _read_device(pynvml: object, handle: object, index: int) -> GpuInfo:
    import pynvml as nv

    name = nv.nvmlDeviceGetName(handle)
    if isinstance(name, bytes):
        name = name.decode()
    mem = nv.nvmlDeviceGetMemoryInfo(handle)
    missing: list[str] = []

    def optional(label: str, fn: object) -> float | None:
        try:
            return float(fn())  # type: ignore[operator]
        except Exception:  # noqa: BLE001 - WSL2 withholds several of these
            missing.append(label)
            return None

    util = optional("utilization_pct", lambda: nv.nvmlDeviceGetUtilizationRates(handle).gpu)
    temp = optional("temperature_c", lambda: nv.nvmlDeviceGetTemperature(handle, 0))
    power = optional("power_w", lambda: nv.nvmlDeviceGetPowerUsage(handle) / 1000.0)
    return GpuInfo(
        index=index,
        name=str(name),
        vram_total_mb=mem.total // (1024 * 1024),
        vram_free_mb=mem.free // (1024 * 1024),
        vram_used_mb=mem.used // (1024 * 1024),
        utilization_pct=int(util) if util is not None else None,
        temperature_c=int(temp) if temp is not None else None,
        power_w=power,
        unavailable_fields=missing,
    )


def probe_host(models_dir: Path) -> HostInfo:
    import psutil

    models_dir.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(models_dir)
    vm = psutil.virtual_memory()
    return HostInfo(
        platform=f"{platform.system()} {platform.release()}",
        is_wsl=is_wsl(),
        ram_total_mb=vm.total // (1024 * 1024),
        ram_available_mb=vm.available // (1024 * 1024),
        cpu_count=os.cpu_count() or 1,
        disk_free_mb=disk.free // (1024 * 1024),
    )


def report(models_dir: Path) -> HardwareReport:
    gpus, nvml = probe_gpus()
    host = probe_host(models_dir)
    notes: list[str] = []
    if host.is_wsl:
        notes.extend([WSL_NVML_HINT, WSL_MOUNT_HINT])
    if not gpus:
        notes.append(
            "No NVIDIA GPU visible. The app runs, but generation will use CPU and be slow; "
            "`make models` will rank the smallest models first."
        )
    for gpu in gpus:
        if gpu.unavailable_fields:
            notes.append(f"{gpu.name}: NVML did not expose {', '.join(gpu.unavailable_fields)}.")
    return HardwareReport(gpus=gpus, host=host, nvml_available=nvml, notes=notes)


class _suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> bool:
        return True
