from pathlib import Path

from career_os.config import settings


class ResumeStore:
    """ResumeStore（ResumeStore）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    def __init__(self) -> None:
        """__init__（初始化对象）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._data_dir = Path(settings.data_dir)
        self._resume_path = self._data_dir / "resume" / "source.md"

    def read(self) -> str:
        """read（read）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        if not self._resume_path.exists():
            self._resume_path.parent.mkdir(parents=True, exist_ok=True)
            self._resume_path.write_text("", encoding="utf-8")
        return self._resume_path.read_text(encoding="utf-8")
