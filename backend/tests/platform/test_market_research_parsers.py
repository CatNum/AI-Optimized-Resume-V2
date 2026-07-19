from __future__ import annotations

import pytest

from career_os.platform.market_research.parsers import parse_salary


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\ue032\ue035-\ue033\ue031K·\ue032\ue034薪", (14000, 20000)),
        ("\ue039-\ue032\ue033K", (8000, 12000)),
    ],
)
def test_parse_salary_decodes_boss_kanzhun_mix_private_use_digits(
    raw: str,
    expected: tuple[int, int],
) -> None:
    """BOSS 的 kanzhun-mix 私有字符数字须在薪资正则解析前还原。"""
    assert parse_salary(raw) == expected
