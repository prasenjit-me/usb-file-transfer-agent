import psutil
import shutil
import ctypes
from pathlib import Path
from typing import List


def get_usb_drives() -> List[dict]:
    drives = []
    for partition in psutil.disk_partitions():
        opts = partition.opts.lower()
        if "removable" in opts or partition.fstype.upper() in ("FAT32", "EXFAT", "FAT"):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "label": _get_label(partition.mountpoint),
                })
            except (PermissionError, OSError):
                pass
    return drives


def _get_label(mountpoint: str) -> str:
    try:
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(mountpoint), buf, ctypes.sizeof(buf),
            None, None, None, None, 0,
        )
        return buf.value if buf.value else "USB Drive"
    except Exception:
        return "USB Drive"


def list_directory(path: str) -> List[dict]:
    items = []
    try:
        p = Path(path)
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "size": stat.st_size if not item.is_dir() else 0,
                })
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return items


def copy_file(src: str, dst_dir: str) -> tuple[bool, str]:
    try:
        src_path = Path(src)
        dst_path = _unique_path(Path(dst_dir) / src_path.name)
        shutil.copy2(src, dst_path)
        return True, str(dst_path)
    except Exception as e:
        return False, str(e)


def move_file(src: str, dst_dir: str) -> tuple[bool, str]:
    try:
        src_path = Path(src)
        dst_path = _unique_path(Path(dst_dir) / src_path.name)
        shutil.move(src, dst_path)
        return True, str(dst_path)
    except Exception as e:
        return False, str(e)


def _unique_path(p: Path) -> Path:
    counter = 1
    result = p
    while result.exists():
        result = p.parent / f"{p.stem} ({counter}){p.suffix}"
        counter += 1
    return result


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"
