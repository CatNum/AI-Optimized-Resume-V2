from typing import Any

from career_os.platform.store.resume import ResumeStore


def resume_read(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """resume_read（resume read）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    content = ResumeStore().read()
    return {"content": content}
