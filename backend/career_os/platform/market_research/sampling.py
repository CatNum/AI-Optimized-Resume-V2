from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from career_os.platform.market_research.models import CollectedJob
from career_os.platform.market_research.parsers import normalize_company_name


@dataclass(frozen=True)
class AdmissionResult:
    """AdmissionResult（样本准入结果）说明岗位是新增、重复合并还是超过公司上限。"""

    status: Literal["accepted", "duplicate", "company_limited"]  # 本次岗位准入分支
    job: CollectedJob | None  # 新增或合并后的岗位；公司超限时为空


class DirectionSample:
    """DirectionSample（方向样本）按岗位身份全局去重，并限制同一公司前五条。"""

    def __init__(self, *, max_jobs_per_company: int = 5) -> None:
        """创建方向内样本索引；max_jobs_per_company 表示每家公司最多接纳的岗位数。"""
        if max_jobs_per_company < 1:
            raise ValueError("max_jobs_per_company must be positive")
        self.max_jobs_per_company = max_jobs_per_company  # 同公司按抓取顺序允许接纳的上限
        self.jobs: list[CollectedJob] = []  # 已接纳且保持抓取顺序的确定性岗位元数据
        self._identity_to_index: dict[str, int] = {}  # 稳定岗位身份到 jobs 下标的索引
        self._company_counts: dict[str, int] = {}  # 规范公司名到已接纳岗位数的计数

    def admit(self, job: CollectedJob, keyword: str) -> AdmissionResult:
        """先合并重复岗位的命中关键词，再对真正新增岗位应用公司上限。"""
        identity = job_identity(job)
        existing_index = self._identity_to_index.get(identity)
        if existing_index is not None:
            existing = self.jobs[existing_index]
            matched_keywords = tuple(dict.fromkeys((*existing.matched_keywords, keyword)))
            merged = existing.model_copy(update={"matched_keywords": matched_keywords})
            self.jobs[existing_index] = merged
            return AdmissionResult(status="duplicate", job=merged)

        company_key = normalize_company_name(job.company_name)
        company_count = self._company_counts.get(company_key, 0)
        if company_count >= self.max_jobs_per_company:
            return AdmissionResult(status="company_limited", job=None)

        accepted = job.model_copy(update={"matched_keywords": (keyword,)})
        self._identity_to_index[identity] = len(self.jobs)
        self._company_counts[company_key] = company_count + 1
        self.jobs.append(accepted)
        return AdmissionResult(status="accepted", job=accepted)


class ScreenshotSampler:
    """ScreenshotSampler（截图抽样器）只在岗位最终入样后独立抽取完整详情页截图。"""

    def __init__(
        self,
        probability: float = 0.1,
        *,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        """配置独立抽样概率和随机数函数；截图不传给 LLM、统计或下游。"""
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be between zero and one")
        self.probability = probability  # 每个最终入样岗位独立命中截图的概率
        self._random_value = random_value  # 生成零到一随机数的可注入函数

    def capture_if_selected(
        self,
        page: Any,
        screenshots_dir: Path,
        job: CollectedJob,
    ) -> Path | None:
        """命中概率时保存完整长截图并返回路径；未命中时不创建任何页面证据。"""
        if self._random_value() >= self.probability:
            return None
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(job_identity(job).encode("utf-8")).hexdigest()
        filename = f"{digest}.png"
        result = page.get_screenshot(
            path=screenshots_dir,
            name=filename,
            full_page=True,
        )
        screenshot_path = Path(result) if isinstance(result, str) else screenshots_dir / filename
        resolved = screenshot_path.resolve()
        if screenshots_dir.resolve() not in resolved.parents or not resolved.is_file():
            raise RuntimeError("full-page audit screenshot was not created in the temp directory")
        return resolved


def job_identity(job: CollectedJob) -> str:
    """返回岗位编号优先、确定性指纹兜底的方向内全局去重身份。"""
    if job.job_id:
        return job.job_id
    if job.fingerprint:
        return job.fingerprint
    raise ValueError("job_id or fingerprint is required")
