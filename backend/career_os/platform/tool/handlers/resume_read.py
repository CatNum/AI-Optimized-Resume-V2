from typing import Any

from career_os.platform.store.resume import ResumeStore


def resume_read(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """读取简历内容。"""
    content = ResumeStore().read()
    return {"content": content}
