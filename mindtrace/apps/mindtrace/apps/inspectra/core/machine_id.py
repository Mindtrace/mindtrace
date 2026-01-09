"""Machine ID generation based on hardware characteristics."""

import hashlib
import platform
import subprocess
import uuid
from typing import List, Optional

# Module-level cache for machine ID
_cached_machine_id: Optional[str] = None


def get_machine_id() -> str:
    """
    Get the cached machine ID, computing it if necessary.

    The machine ID is computed once and cached for the lifetime of the process.
    """
    global _cached_machine_id
    if _cached_machine_id is None:
        _cached_machine_id = _compute_machine_id()
    return _cached_machine_id


def _compute_machine_id() -> str:
    """
    Generate a unique machine identifier based on hardware characteristics.

    Uses a combination of:
    - MAC address
    - CPU info
    - Platform info
    - Disk serial (if available on Linux)
    - Windows machine GUID (if on Windows)

    Returns a SHA-256 hash of the combined identifiers.
    """
    identifiers: List[str] = []

    # MAC address
    try:
        mac = uuid.getnode()
        identifiers.append(f"mac:{mac}")
    except Exception:
        pass

    # Platform info
    try:
        identifiers.append(f"platform:{platform.platform()}")
        identifiers.append(f"machine:{platform.machine()}")
        identifiers.append(f"processor:{platform.processor()}")
    except Exception:
        pass

    # CPU info (Linux)
    try:
        if platform.system() == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "Serial" in line or "model name" in line:
                        identifiers.append(f"cpu:{line.strip()}")
                        break
    except Exception:
        pass

    # Disk serial (Linux)
    try:
        if platform.system() == "Linux":
            result = subprocess.run(
                ["lsblk", "-o", "SERIAL", "-n", "-d"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                serial = result.stdout.strip().split()[0]
                if serial:
                    identifiers.append(f"disk:{serial}")
    except Exception:
        pass

    # Machine ID file (Linux)
    try:
        if platform.system() == "Linux":
            with open("/etc/machine-id", "r") as f:
                machine_id = f.read().strip()
                if machine_id:
                    identifiers.append(f"machine_id:{machine_id}")
    except Exception:
        pass

    # Windows machine GUID
    try:
        if platform.system() == "Windows":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            )
            machine_guid = winreg.QueryValueEx(key, "MachineGuid")[0]
            identifiers.append(f"windows_guid:{machine_guid}")
    except Exception:
        pass

    # macOS hardware UUID
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["system_profiler", "SPHardwareDataType"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "Hardware UUID" in line:
                        hw_uuid = line.split(":")[-1].strip()
                        identifiers.append(f"macos_uuid:{hw_uuid}")
                        break
    except Exception:
        pass

    # Combine and hash
    combined = "|".join(sorted(identifiers))
    return hashlib.sha256(combined.encode()).hexdigest()
