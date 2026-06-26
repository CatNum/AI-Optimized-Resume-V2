from dataclasses import dataclass


@dataclass
class HarnessError:
    """HarnessError（运行时错误）表示 Harness 层返回的业务错误。

    code（错误码）用于程序判断错误类型；message（错误消息）用于展示或写入 trace。
    """
    code: str
    message: str
