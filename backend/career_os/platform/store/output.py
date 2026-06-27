import threading
from datetime import date
from pathlib import Path

from career_os.config import settings

_lock = threading.Lock()


class OutputStore:
    """
    OutputStore（产物存储）负责按日期目录读写和删除输出文件。
    """

    def __init__(self) -> None:
        """初始化对象。"""
        self._output_dir = Path(settings.output_dir)

    def _day_dir(self, day: date | None = None) -> Path:
        """处理day dir。"""
        target = day or date.today()
        return self._output_dir / target.isoformat()

    def write(self, filename: str, content: str, day: date | None = None) -> Path:
        """处理write。"""
        with _lock:
            target_dir = self._day_dir(day)
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / filename
            path.write_text(content, encoding="utf-8")
            return path

    def list_outputs(self, day: date | None = None) -> list[Path]:
        """列出outputs。"""
        with _lock:
            target_dir = self._day_dir(day)
            if not target_dir.exists():
                return []
            return sorted(p for p in target_dir.iterdir() if p.is_file())

    def list_all_files(self) -> list[Path]:
        """列出all files。"""
        with _lock:
            if not self._output_dir.exists():
                return []
            files: list[Path] = []
            for day_dir in self._output_dir.iterdir():
                if not day_dir.is_dir():
                    continue
                files.extend(p for p in day_dir.iterdir() if p.is_file())
            return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def delete(self, path: Path) -> bool:
        """处理delete。"""
        with _lock:
            resolved = path.resolve()
            output_root = self._output_dir.resolve()
            if output_root not in resolved.parents and resolved != output_root:
                return False
            if resolved.exists() and resolved.is_file():
                resolved.unlink()
                return True
            return False
