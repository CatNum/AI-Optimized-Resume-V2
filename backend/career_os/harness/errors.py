from dataclasses import dataclass


@dataclass
class HarnessError:
    code: str
    message: str
