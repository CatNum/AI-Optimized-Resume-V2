from dataclasses import dataclass


@dataclass
class HarnessError:
    """
    HarnessError（运行时错误）表示 Harness 层返回的业务错误。
    """

    code: str  # 错误码
    message: str  # 错误消息
