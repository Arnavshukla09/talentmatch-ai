"""
Single source of truth for compute device selection.

The original notebook defined DeviceManager three separate times (once per
phase bootstrap cell), each slightly different. This is the one canonical
version every module should import from.
"""

from __future__ import annotations

import platform
from typing import Any, Dict, Literal

import torch

Device = Literal["cuda", "mps", "cpu"]


class DeviceManager:
    """Resolves the best available compute device, with CPU fallback."""

    @staticmethod
    def get_device() -> Device:
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def get_device_info() -> Dict[str, Any]:
        device = DeviceManager.get_device()
        info: Dict[str, Any] = {
            "device": device,
            "torch_version": torch.__version__,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        }
        if device == "cuda":
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_memory_total_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024**3), 2
            )
            info["cuda_version"] = torch.version.cuda
        return info


DEVICE: Device = DeviceManager.get_device()
