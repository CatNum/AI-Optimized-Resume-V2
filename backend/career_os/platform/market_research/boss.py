from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urljoin, urlsplit

from career_os.config import settings
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    CollectedJob,
    DirectionPlan,
    ResearchStage,
)
from career_os.platform.market_research.page_contracts import (
    BossPageContract,
    PageChangedError,
    PageField,
    validate_external_url,
)
from career_os.platform.market_research.parsers import (
    has_basic_job_content,
    normalize_company_name,
    normalize_description,
    normalize_education,
    normalize_experience,
    normalize_recruiter_activity,
    parse_salary,
)
from career_os.platform.market_research.sampling import (
    DirectionSample,
    ScreenshotSampler,
    job_identity,
)
from career_os.platform.market_research.store import MarketResearchStore

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import (
        DirectionRunContext,
        MarketResearchRunner,
        StageHandler,
    )


_BOSS_CITY_CODES = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "深圳": "101280600",
    "杭州": "101210100",
    "广州": "101280100",
    "成都": "101270100",
    "南京": "101190100",
    "武汉": "101200100",
    "西安": "101110100",
    "苏州": "101190400",
}
_JOB_ID_PATTERN = re.compile(r"/job_detail/([^./?#]+)(?:\.html)?")
_SAMPLE_LIMITATIONS = (
    "BOSS 默认排序可能影响本次岗位样本。",
    "账号登录状态和平台个性化推荐可能影响本次岗位样本。",
    "本次结果是受预算、关键词、城市顺序和公司上限约束的当前页面样本。",
)


@dataclass(frozen=True)
class BossCollectionResult:
    """BossCollectionResult（BOSS 采集结果）保存确定性岗位、运行内存 JD 和执行口径。"""

    jobs: tuple[CollectedJob, ...]  # 最终去重并应用公司上限后的岗位元数据
    raw_job_descriptions: dict[str, str]  # 仅存活于 Runner 线程内存、供 Task 9 提取的原始 JD
    visited_cities: tuple[str, ...]  # 实际开始访问过的城市顺序
    keyword_statuses: dict[str, str]  # 每个 BOSS 关键词的 completed/cutoff/not_run 状态
    screenshot_paths: tuple[str, ...]  # 临时审计截图绝对路径，发布时转换为正式引用
    sample_limitations: tuple[str, ...]  # 必须进入最终报告的样本边界


class BossJobCollector:
    """BossJobCollector（BOSS 岗位采集器）在单标签页中严格串行采集当前全职岗位。"""

    def __init__(
        self,
        store: MarketResearchStore,
        *,
        contract: BossPageContract | None = None,
        screenshot_sampler: ScreenshotSampler | None = None,
        restart_handler: Callable[[], Any] | None = None,
        user_action_handler: Callable[[str], None] | None = None,
        progress_handler: Callable[[DirectionRunContext, str, str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        uniform: Callable[[float, float], float] = random.uniform,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """注入 Store、页面回调、低频等待和随机抽样 seam，真实与 Fake 页面遵守同一接口。"""
        self.store = store  # 临时截图目录所属的市场调研存储器
        self.contract = contract or BossPageContract()  # 当前版本化 BOSS 页面字段契约
        self.screenshot_sampler = screenshot_sampler or ScreenshotSampler(
            settings.market_research.screenshot_probability
        )  # 仅对最终新增岗位执行的独立截图抽样器
        self.restart_handler = restart_handler  # 列表技术失败后唯一一次重启专用 Chrome 的回调
        self.user_action_handler = user_action_handler  # 登录或验证时暂停 Runner 的回调
        self.progress_handler = progress_handler  # 每个新增有效岗位后的状态快照更新回调
        self._sleep = sleep  # 点击、返回、切换和滚动后的低频等待函数
        self._uniform = uniform  # 从配置区间选择等待秒数的随机函数
        self._now = now or (lambda: datetime.now(UTC))  # 生成 collected_at（采集时间）的时钟

    def collect(self, context: DirectionRunContext, page: Any) -> BossCollectionResult:
        """按关键词和城市顺序采集；重复岗位不占每关键词三十条新增额度。"""
        direction = context.direction
        sample = DirectionSample(max_jobs_per_company=context.plan.filter_policy.max_jobs_per_company)
        raw_job_descriptions: dict[str, str] = {}
        visited_cities: list[str] = []
        screenshot_paths: list[str] = []
        keyword_statuses = {keyword: "not_run" for keyword in direction.boss_keywords}
        screenshots_dir = (
            self.store.direction_temp_dir(context.research_id, context.direction_run_id)
            / "screenshots"
        )
        active_page = page

        for keyword in direction.boss_keywords:
            self._require_budget(context)
            new_for_keyword = 0
            keyword_statuses[keyword] = "completed"
            for city in direction.cities:
                self._require_budget(context)
                if new_for_keyword >= settings.market_research.target_jobs_per_keyword:
                    keyword_statuses[keyword] = "cutoff"
                    break
                if city not in visited_cities:
                    visited_cities.append(city)
                city_code = resolve_boss_city_code(city)
                list_url = self.contract.build_search_url(keyword, city_code)
                active_page = self._load_list_with_recovery(
                    active_page,
                    list_url,
                    context,
                )
                context.data["page"] = active_page
                self._wait_condition_change()
                seen_card_urls: set[str] = set()
                empty_scrolls = 0

                while empty_scrolls < 3:
                    self._require_budget(context)
                    card_urls = self._read_card_urls(active_page)
                    new_urls = [url for url in card_urls if url not in seen_card_urls]
                    if not new_urls:
                        empty_scrolls += 1
                    else:
                        empty_scrolls = 0
                    seen_card_urls.update(new_urls)

                    for job_url in new_urls:
                        self._require_budget(context)
                        if new_for_keyword >= settings.market_research.target_jobs_per_keyword:
                            keyword_statuses[keyword] = "cutoff"
                            break
                        context.candidate_count += 1
                        draft = self._collect_detail(active_page, job_url, keyword, context)
                        self._return_to_list(active_page, list_url)
                        if draft is None:
                            continue
                        job, raw_description = draft
                        admission = sample.admit(job, keyword)
                        if admission.status == "duplicate":
                            continue
                        if admission.status == "company_limited" or admission.job is None:
                            continue

                        accepted = admission.job
                        identity = job_identity(accepted)
                        raw_job_descriptions[identity] = raw_description
                        context.valid_job_count = len(sample.jobs)
                        new_for_keyword += 1
                        screenshot_path = self._capture_audit_screenshot(
                            active_page,
                            screenshots_dir,
                            accepted,
                            job_url,
                        )
                        self._return_to_list(active_page, list_url)
                        if screenshot_path is not None:
                            screenshot_paths.append(str(screenshot_path))
                        if self.progress_handler is not None:
                            self.progress_handler(context, keyword, city)

                    if keyword_statuses[keyword] == "cutoff":
                        break
                    active_page.scroll.down(900)
                    self._wait_click_or_return()

                if keyword_statuses[keyword] == "cutoff":
                    break
            self._wait_condition_change()

        return BossCollectionResult(
            jobs=tuple(sample.jobs),
            raw_job_descriptions=raw_job_descriptions,
            visited_cities=tuple(visited_cities),
            keyword_statuses=keyword_statuses,
            screenshot_paths=tuple(screenshot_paths),
            sample_limitations=_SAMPLE_LIMITATIONS,
        )

    def _load_list_with_recovery(
        self,
        page: Any,
        list_url: str,
        context: DirectionRunContext,
    ) -> Any:
        """列表最多重试两次；仍失败时只重启一次专用 Chrome，再执行同样重试。"""
        active_page = page
        last_error: Exception | None = None
        for recovery_round in range(2):
            for _attempt in range(settings.market_research.boss_list_retry_times + 1):
                self._require_budget(context)
                try:
                    self._navigate(active_page, list_url)
                    self._handle_user_action(active_page, list_url)
                    list_element = self.contract.read_required(
                        active_page,
                        self.contract.job_list,
                        stage=ResearchStage.COLLECTING_BOSS.value,
                    )
                    if list_element is None:
                        raise RuntimeError("BOSS list is unavailable")
                    self._ensure_full_time(active_page)
                    return active_page
                except PageChangedError:
                    raise
                except Exception as error:
                    last_error = error
            if recovery_round == 0 and self.restart_handler is not None:
                active_page = self.restart_handler()
                context.data["page"] = active_page
                continue
            break
        raise MarketResearchError(
            MarketResearchErrorCode.EXECUTION_FAILED,
            stage=ResearchStage.COLLECTING_BOSS.value,
            message=type(last_error).__name__ if last_error is not None else "BOSS list failed",
        ) from last_error

    def _collect_detail(
        self,
        page: Any,
        job_url: str,
        keyword: str,
        context: DirectionRunContext,
    ) -> tuple[CollectedJob, str] | None:
        """详情页最多重试两次；业务准入失败直接跳过，页面契约变化立即停止方向。"""
        for _attempt in range(settings.market_research.job_detail_retry_times + 1):
            self._require_budget(context)
            try:
                self._navigate(page, job_url)
                self._wait_click_or_return()
                self._handle_user_action(page, job_url)
                return self._parse_detail(page, job_url, keyword)
            except PageChangedError:
                raise
            except _InvalidJob:
                return None
            except Exception:
                continue
        return None

    def _parse_detail(
        self,
        page: Any,
        job_url: str,
        keyword: str,
    ) -> tuple[CollectedJob, str]:
        """以详情页为准构造仅含确定性元数据的岗位，原始 JD 只随返回值留在内存。"""
        stage = ResearchStage.COLLECTING_BOSS.value
        if self.contract.read_optional(page, self.contract.detail_closed_marker) is not None:
            raise _InvalidJob()
        employment = _required_text(page, self.contract, self.contract.detail_employment_type, stage)
        if "全职" not in employment:
            raise _InvalidJob()
        title = _required_text(page, self.contract, self.contract.detail_title, stage)
        salary_raw = _required_text(page, self.contract, self.contract.detail_salary, stage)
        salary = parse_salary(salary_raw)
        if salary is None:
            raise _InvalidJob()
        city = _required_text(page, self.contract, self.contract.detail_city, stage)
        activity_raw = _required_text(page, self.contract, self.contract.recruiter_activity, stage)
        activity = normalize_recruiter_activity(activity_raw)
        if activity is None:
            raise _InvalidJob()
        company_name = _required_text(page, self.contract, self.contract.company_name, stage)
        raw_description = _required_text(page, self.contract, self.contract.job_description, stage)
        if not has_basic_job_content(raw_description):
            raise _InvalidJob()

        experience_raw, experience_group = normalize_experience(
            _optional_text(page, self.contract, self.contract.detail_experience)
        )
        education_raw, education_group = normalize_education(
            _optional_text(page, self.contract, self.contract.detail_education)
        )
        job_id = _job_id_from_url(job_url)
        fingerprint = None
        if job_id is None:
            fingerprint = _build_fingerprint(
                company_name=company_name,
                title=title,
                city=city,
                salary_min=salary[0],
                salary_max=salary[1],
                raw_description=raw_description,
            )
        job = CollectedJob(
            job_id=job_id,
            fingerprint=fingerprint,
            job_url=job_url,
            title=title,
            matched_keywords=(keyword,),
            city=city,
            experience_raw=experience_raw,
            experience_group=experience_group,
            education_raw=education_raw,
            education_group=education_group,
            salary_min=salary[0],
            salary_max=salary[1],
            recruiter_activity=activity,
            company_id=None,
            company_name=company_name,
            company_industry=_optional_text(page, self.contract, self.contract.company_industry),
            company_size=_optional_text(page, self.contract, self.contract.company_size),
            collected_at=self._now(),
            collection_valid=True,
        )
        return job, raw_description

    def _read_card_urls(self, page: Any) -> list[str]:
        """读取当前列表可见岗位卡的官方详情 URL，JD 中的任何链接都不会经过此函数。"""
        cards = self.contract.read_all_required(
            page,
            self.contract.job_card,
            stage=ResearchStage.COLLECTING_BOSS.value,
        )
        urls: list[str] = []
        for card in cards:
            link = _find_in_element(card, self.contract.job_card_link)
            href = _element_attribute(link, "href") if link is not None else None
            if not href:
                continue
            absolute = urljoin("https://www.zhipin.com", href)
            try:
                safe_url = validate_external_url(absolute, self.contract.allowed_hosts)
            except ValueError:
                continue
            if "/job_detail/" in urlsplit(safe_url).path:
                urls.append(safe_url)
        return list(dict.fromkeys(urls))

    def _ensure_full_time(self, page: Any) -> None:
        """确认并设置全职筛选，不设置发布日期过滤或改变 BOSS 默认排序。"""
        field = self.contract.read_required(
            page,
            self.contract.full_time_filter,
            stage=ResearchStage.COLLECTING_BOSS.value,
        )
        class_name = (_element_attribute(field, "class") or "").casefold()
        if not any(marker in class_name for marker in ("active", "selected", "checked")):
            field.click()
            self._wait_click_or_return()

    def _capture_audit_screenshot(
        self,
        page: Any,
        screenshots_dir: Path,
        job: CollectedJob,
        job_url: str,
    ) -> Path | None:
        """重新打开已入样详情页后执行独立抽样；失败截图不会退化为 DOM 或局部原文。"""
        try:
            self._navigate(page, job_url)
            self._wait_click_or_return()
            self._handle_user_action(page, job_url)
            return self.screenshot_sampler.capture_if_selected(page, screenshots_dir, job)
        except PageChangedError:
            raise
        except Exception as error:
            raise MarketResearchError(
                MarketResearchErrorCode.STORAGE_FAILED,
                stage=ResearchStage.COLLECTING_BOSS.value,
                message=type(error).__name__,
            ) from error

    def _navigate(self, page: Any, url: str) -> None:
        """每次列表和详情导航前复核 BOSS 官方 HTTPS 白名单。"""
        safe_url = validate_external_url(url, self.contract.allowed_hosts)
        page.get(safe_url)

    def _handle_user_action(self, page: Any, target_url: str) -> None:
        """检测登录或验证页面并交给 Runner 无限等待；采集器不输入任何凭据。"""
        if not self.contract.user_action_required(page):
            return
        if self.user_action_handler is None:
            raise RuntimeError("BOSS user action handler is not configured")
        self.user_action_handler(target_url)

    def _return_to_list(self, page: Any, list_url: str) -> None:
        """详情处理后返回原列表；浏览器历史异常时仍只导航到已校验官方列表 URL。"""
        try:
            page.back()
            current_url = str(getattr(page, "url", "") or "")
            validate_external_url(current_url, self.contract.allowed_hosts)
            if current_url.split("#", 1)[0] != list_url.split("#", 1)[0]:
                self._navigate(page, list_url)
        except Exception:
            self._navigate(page, list_url)
        self._wait_click_or_return()

    def _require_budget(self, context: DirectionRunContext) -> None:
        """在每个页面安全检查点拒绝继续消耗已经归零的方向有效预算。"""
        if context.budget.remaining_seconds() <= 0:
            raise MarketResearchError(
                MarketResearchErrorCode.BUDGET_EXHAUSTED,
                stage=ResearchStage.COLLECTING_BOSS.value,
            )

    def _wait_click_or_return(self) -> None:
        """点击或返回后按集中配置等待 1.5 到 3 秒。"""
        self._sleep(
            self._uniform(
                settings.market_research.click_wait_min_seconds,
                settings.market_research.click_wait_max_seconds,
            )
        )

    def _wait_condition_change(self) -> None:
        """切换关键词或城市后按集中配置等待 2 到 5 秒。"""
        self._sleep(
            self._uniform(
                settings.market_research.condition_wait_min_seconds,
                settings.market_research.condition_wait_max_seconds,
            )
        )


def build_boss_stage_handler(
    collector: BossJobCollector,
) -> StageHandler:
    """创建 collecting_boss（BOSS 采集）阶段处理器并写入方向线程内存。"""

    def collect_boss(context: DirectionRunContext) -> None:
        """复用专用单标签页采集确定性岗位，并暂存 Task 9 所需的内存 JD。"""
        result = collector.collect(context, context.require_browser_page())
        context.record_boss_results(result)

    return collect_boss


def resolve_boss_city_code(city: str) -> str:
    """把用户确认的城市名映射为 BOSS 官方搜索城市编码；未知城市明确拒绝猜测。"""
    code = _BOSS_CITY_CODES.get(city.strip())
    if code is None:
        raise ValueError(f"unsupported BOSS city: {city}")
    return code


class _InvalidJob(Exception):
    """_InvalidJob（岗位未通过准入）用于跳过业务无效详情，不把方向标记为技术失败。"""


def _required_text(
    page: Any,
    contract: BossPageContract,
    field: PageField,
    stage: str,
) -> str:
    """读取必需详情字段的可见文本；空文本视为页面契约变化。"""
    element = contract.read_required(page, field, stage=stage)
    value = _element_text(element)
    if not value:
        raise PageChangedError(contract.contract_version, stage, field.field_name)
    return value


def _optional_text(page: Any, contract: BossPageContract, field: PageField) -> str | None:
    """读取允许缺失的详情字段文本，缺失或空值返回空。"""
    element = contract.read_optional(page, field)
    if element is None:
        return None
    return _element_text(element) or None


def _element_text(element: Any) -> str:
    """读取单个字段元素的直接可见文本，不读取整页 DOM。"""
    value = getattr(element, "text", None)
    return value.strip() if isinstance(value, str) else ""


def _element_attribute(element: Any, name: str) -> str | None:
    """读取岗位卡链接或筛选状态的单个属性，不遍历 HTML。"""
    try:
        value = element.attr(name)
    except Exception:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _find_in_element(element: Any, field: PageField) -> Any | None:
    """按契约定位器顺序查找岗位卡内部字段。"""
    for locator in field.locators:
        try:
            found = element.ele(locator, timeout=0.2)
        except Exception:
            continue
        if found:
            return found
    return None


def _job_id_from_url(job_url: str) -> str | None:
    """从已校验 BOSS 详情 URL 提取稳定岗位编号，无法提取时交给指纹兜底。"""
    match = _JOB_ID_PATTERN.search(urlsplit(job_url).path)
    return match.group(1) if match is not None else None


def _build_fingerprint(
    *,
    company_name: str,
    title: str,
    city: str,
    salary_min: int,
    salary_max: int,
    raw_description: str,
) -> str:
    """用规范公司、标题、城市、薪资和内存清洗 JD 生成 SHA-256 岗位指纹。"""
    payload = "\n".join(
        (
            normalize_company_name(company_name),
            title.strip().casefold(),
            city.strip().casefold(),
            str(salary_min),
            str(salary_max),
            normalize_description(raw_description),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
