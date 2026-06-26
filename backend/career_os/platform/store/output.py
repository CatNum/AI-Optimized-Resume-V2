import threading
from datetime import date
from pathlib import Path

from career_os.config import settings

_lock = threading.Lock()


class OutputStore:
    """OutputStore（OutputStore）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    def __init__(self) -> None:
        """__init__（初始化对象）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._output_dir = Path(settings.output_dir)

    def _day_dir(self, day: date | None = None) -> Path:
        """_day_dir（内部函数 day dir）的函数说明。

        day（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        target = day or date.today()
        return self._output_dir / target.isoformat()

    def write(self, filename: str, content: str, day: date | None = None) -> Path:
        """write（write）的函数说明。

        filename（参数）、content（参数）、day（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _lock:
            target_dir = self._day_dir(day)
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / filename
            path.write_text(content, encoding="utf-8")
            return path

    def list_outputs(self, day: date | None = None) -> list[Path]:
        """list_outputs（list outputs）的函数说明。

        day（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _lock:
            target_dir = self._day_dir(day)
            if not target_dir.exists():
                return []
            return sorted(p for p in target_dir.iterdir() if p.is_file())

    def list_all_files(self) -> list[Path]:
        """list_all_files（list all files）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """delete（delete）的函数说明。

        path（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _lock:
            resolved = path.resolve()
            output_root = self._output_dir.resolve()
            if output_root not in resolved.parents and resolved != output_root:
                return False
            if resolved.exists() and resolved.is_file():
                resolved.unlink()
                return True
            return False
