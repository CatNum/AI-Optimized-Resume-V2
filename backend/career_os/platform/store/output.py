import threading
from datetime import date
from pathlib import Path

from career_os.config import settings

_lock = threading.Lock()


class OutputStore:
    def __init__(self) -> None:
        self._output_dir = Path(settings.output_dir)

    def _day_dir(self, day: date | None = None) -> Path:
        target = day or date.today()
        return self._output_dir / target.isoformat()

    def write(self, filename: str, content: str, day: date | None = None) -> Path:
        with _lock:
            target_dir = self._day_dir(day)
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / filename
            path.write_text(content, encoding="utf-8")
            return path

    def list_outputs(self, day: date | None = None) -> list[Path]:
        with _lock:
            target_dir = self._day_dir(day)
            if not target_dir.exists():
                return []
            return sorted(p for p in target_dir.iterdir() if p.is_file())

    def delete(self, path: Path) -> bool:
        with _lock:
            resolved = path.resolve()
            output_root = self._output_dir.resolve()
            if output_root not in resolved.parents and resolved != output_root:
                return False
            if resolved.exists() and resolved.is_file():
                resolved.unlink()
                return True
            return False
