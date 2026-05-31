from typing import Any

from career_os.platform.store.resume import ResumeStore


def resume_read(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    content = ResumeStore().read()
    return {"content": content}
