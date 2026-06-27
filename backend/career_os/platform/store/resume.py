from pathlib import Path

from career_os.config import settings


class ResumeStore:
    """
    ResumeStore（简历存储）负责读取本地简历源文本。
    """

    def __init__(self) -> None:
        """初始化对象。"""
        self._data_dir = Path(settings.data_dir)
        self._resume_path = self._data_dir / "resume" / "source.md"

    def read(self) -> str:
        """处理read。"""
        if not self._resume_path.exists():
            self._resume_path.parent.mkdir(parents=True, exist_ok=True)
            self._resume_path.write_text("", encoding="utf-8")
        return self._resume_path.read_text(encoding="utf-8")
