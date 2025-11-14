"""
Hardware detection utilities for Raspberry Pi models.
"""

import multiprocessing
from pathlib import Path
from typing import Literal, Optional


def detect_pi_model() -> Optional[Literal["pi_zero_w", "pi_zero_2_w", "other"]]:
    """
    Detect Raspberry Pi model from /proc/cpuinfo and /proc/device-tree/model.

    Returns:
        "pi_zero_w": Raspberry Pi Zero W (BCM2835, 1 core, ARMv6)
        "pi_zero_2_w": Raspberry Pi Zero 2 W (BCM2837, 4 cores, ARMv7)
        "other": Other Pi models or unknown
        None: Not a Raspberry Pi or detection failed
    """
    try:
        # Try to read device-tree model first (most reliable)
        model_file = Path("/proc/device-tree/model")
        if model_file.exists():
            model_str = model_file.read_text().strip("\x00").lower()

            if "pi zero 2" in model_str:
                return "pi_zero_2_w"
            elif "pi zero" in model_str:
                return "pi_zero_w"
            elif "raspberry pi" in model_str:
                return "other"

        # Fallback: check /proc/cpuinfo
        cpuinfo_file = Path("/proc/cpuinfo")
        if not cpuinfo_file.exists():
            return None

        cpuinfo = cpuinfo_file.read_text()

        # Count CPU cores
        cpu_count = multiprocessing.cpu_count()

        # Check for BCM chip model
        is_bcm2835 = "BCM2835" in cpuinfo
        is_bcm2836 = "BCM2836" in cpuinfo
        is_bcm2837 = "BCM2837" in cpuinfo

        # Pi Zero W: BCM2835, 1 core
        if is_bcm2835 and cpu_count == 1:
            return "pi_zero_w"

        # Pi Zero 2 W: BCM2837, 4 cores (or BCM2710 in some cases)
        # Also check for Cortex-A53 which is specific to Pi Zero 2 W
        if (is_bcm2837 or "Cortex-A53" in cpuinfo) and cpu_count == 4:
            # Could be Pi 3, need to distinguish
            # Pi Zero 2 W has 512MB RAM max
            meminfo = Path("/proc/meminfo").read_text()
            mem_kb = int(
                [line for line in meminfo.split("\n") if "MemTotal" in line][0].split()[
                    1
                ]
            )
            mem_mb = mem_kb // 1024

            if mem_mb < 700:  # Pi Zero 2 W has 512MB
                return "pi_zero_2_w"
            else:
                return "other"  # Pi 3 or 4

        # Other Pi models
        if is_bcm2835 or is_bcm2836 or is_bcm2837:
            return "other"

        return None

    except Exception as e:
        print(f"Hardware detection failed: {e}")
        return None


def can_use_vosk() -> bool:
    """
    Determine if Vosk ASR can be used on this hardware.

    Returns:
        True if Pi Zero 2 W or better (4+ cores, 512MB+ RAM)
        False for Pi Zero W (1 core, too slow for Vosk)
    """
    model = detect_pi_model()

    if model == "pi_zero_2_w":
        return True
    elif model == "other":
        # Other Pi models (Pi 3, 4, etc.) can use Vosk
        return True
    else:
        # Pi Zero W or unknown - stick with Kaldi
        return False


if __name__ == "__main__":
    # Test hardware detection
    model = detect_pi_model()
    print(f"Detected Pi model: {model}")
    print(f"Can use Vosk: {can_use_vosk()}")
