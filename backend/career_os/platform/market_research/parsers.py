from __future__ import annotations

import math
import re
import unicodedata

from career_os.platform.market_research.models import RecruiterActivity


_SPACE_PATTERN = re.compile(r"\s+")
_EXTRA_MONTHS_PATTERN = re.compile(r"[·・]\s*\d+\s*薪", re.IGNORECASE)
_MONTHLY_K_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*[kK]\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*[kK]\s*(?:/月)?$"
)
_MONTHLY_SHARED_K_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*[kK]\s*(?:/月)?$"
)
_ANNUAL_WAN_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(?:万|w|W)\s*[-~—–至]\s*"
    r"(\d+(?:\.\d+)?)\s*(?:万|w|W)\s*/?年$"
)
_ANNUAL_SHARED_WAN_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*"
    r"(?:万|w|W)\s*/?年$"
)


def parse_salary(raw: str | None) -> tuple[int, int] | None:
    """解析双边税前人民币薪资并返回元/月上下限；单边或非月薪语义返回空值。"""
    if not isinstance(raw, str):
        return None
    normalized = unicodedata.normalize("NFKC", raw).strip()
    normalized = _EXTRA_MONTHS_PATTERN.sub("", normalized)
    normalized = _SPACE_PATTERN.sub("", normalized)
    lowered = normalized.casefold()
    if not normalized or any(token in lowered for token in ("面议", "时", "天", "日薪", "周")):
        return None

    monthly_match = _MONTHLY_K_PATTERN.fullmatch(normalized)
    if monthly_match is None:
        monthly_match = _MONTHLY_SHARED_K_PATTERN.fullmatch(normalized)
    if monthly_match is not None:
        salary_min = int(float(monthly_match.group(1)) * 1000)
        salary_max = int(float(monthly_match.group(2)) * 1000)
        return _valid_salary_range(salary_min, salary_max)

    annual_match = _ANNUAL_WAN_PATTERN.fullmatch(normalized)
    if annual_match is None:
        annual_match = _ANNUAL_SHARED_WAN_PATTERN.fullmatch(normalized)
    if annual_match is not None:
        salary_min = math.floor(float(annual_match.group(1)) * 10000 / 12)
        salary_max = math.ceil(float(annual_match.group(2)) * 10000 / 12)
        return _valid_salary_range(salary_min, salary_max)
    return None


def normalize_experience(raw: str | None) -> tuple[str | None, str]:
    """保留页面经验原值并映射到固定经验分组；未知新标签进入“未识别”。"""
    value = _clean_optional_text(raw)
    if value is None:
        return None, "未识别"
    compact = _SPACE_PATTERN.sub("", value)
    exact_groups = {
        "经验不限": "不限",
        "不限": "不限",
        "应届生": "应届生",
        "在校生": "在校生",
        "1年以内": "1 年以内",
        "1-3年": "1-3 年",
        "3-5年": "3-5 年",
        "5-10年": "5-10 年",
        "10年以上": "10 年以上",
    }
    return value, exact_groups.get(compact, "未识别")


def normalize_education(raw: str | None) -> tuple[str | None, str]:
    """保留页面学历原值并映射到固定学历分组；未知新标签进入“未识别”。"""
    value = _clean_optional_text(raw)
    if value is None:
        return None, "未识别"
    compact = _SPACE_PATTERN.sub("", value)
    exact_groups = {
        "学历不限": "不限",
        "不限": "不限",
        "初中及以下": "初中及以下",
        "中专/中技": "中专/中技",
        "高中": "高中",
        "大专": "大专",
        "本科": "本科",
        "硕士": "硕士",
        "博士": "博士",
    }
    return value, exact_groups.get(compact, "未识别")


def normalize_recruiter_activity(raw: str | None) -> RecruiterActivity | None:
    """把页面活跃度去除空白后映射为公共契约值，仅返回允许进入样本的三类。"""
    value = _clean_optional_text(raw)
    if value is None:
        return None
    compact = _SPACE_PATTERN.sub("", value)
    mapping = {
        "刚刚活跃": RecruiterActivity.JUST_ACTIVE,
        "今日活跃": RecruiterActivity.ACTIVE_TODAY,
        "3日内活跃": RecruiterActivity.ACTIVE_WITHIN_THREE_DAYS,
    }
    return mapping.get(compact)


def is_allowed_recruiter_activity(raw: str | None) -> bool:
    """判断页面招聘者活跃度是否属于刚刚、今日或 3 日内活跃。"""
    return normalize_recruiter_activity(raw) is not None


def normalize_company_name(raw: str) -> str:
    """规范公司名用于同方向公司上限和无岗位编号时的确定性指纹。"""
    normalized = unicodedata.normalize("NFKC", raw)
    return _SPACE_PATTERN.sub("", normalized).casefold()


def normalize_description(raw: str) -> str:
    """清洗内存中的 JD 空白用于指纹计算；返回值不得写入持久化文件。"""
    normalized = unicodedata.normalize("NFKC", raw)
    return " ".join(normalized.strip().split()).casefold()


def has_basic_job_content(raw: str | None) -> bool:
    """判断内存 JD 是否至少包含可辨认的职责或要求，不返回或持久化原文片段。"""
    if not isinstance(raw, str):
        return False
    normalized = "".join(unicodedata.normalize("NFKC", raw).split())
    if len(normalized) < 20:
        return False
    markers = ("岗位职责", "职位描述", "工作内容", "负责", "任职要求", "岗位要求", "要求")
    return any(marker in normalized for marker in markers)


def _clean_optional_text(raw: str | None) -> str | None:
    """规范可选页面文本的 Unicode 与首尾空白，空字符串转换为空值。"""
    if not isinstance(raw, str):
        return None
    value = unicodedata.normalize("NFKC", raw).strip()
    return value or None


def _valid_salary_range(salary_min: int, salary_max: int) -> tuple[int, int] | None:
    """只接受大于零且上限不低于下限的双边月薪范围。"""
    if salary_min <= 0 or salary_max < salary_min:
        return None
    return salary_min, salary_max
