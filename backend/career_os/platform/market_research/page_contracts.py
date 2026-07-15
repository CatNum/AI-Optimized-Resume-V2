from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)


_SHORT_LINK_HOSTS = frozenset(
    {
        "bit.ly",
        "dwz.cn",
        "suo.im",
        "t.co",
        "tinyurl.com",
        "url.cn",
    }
)


@dataclass(frozen=True)
class PageField:
    """PageField（页面字段）定义一个业务字段按优先级尝试的版本化定位器。"""

    field_name: str  # 稳定业务字段名，用于解析结果和 page_changed 诊断
    locators: tuple[str, ...]  # DrissionPage 按顺序尝试的 CSS、XPath 或文本定位器


class PageChangedError(MarketResearchError):
    """PageChangedError（页面契约变化错误）携带契约版本、阶段和失败字段名。"""

    def __init__(self, contract_version: str, stage: str, field_name: str) -> None:
        """创建不包含 DOM、页面原文或截图的结构化 page_changed 异常。"""
        self.contract_version = contract_version  # 读取页面时使用的字段契约版本
        self.field_name = field_name  # 无法可靠定位的关键页面字段名
        super().__init__(
            MarketResearchErrorCode.PAGE_CHANGED,
            stage=stage,
            message=(
                f"page_changed contract={contract_version} "
                f"stage={stage} field={field_name}"
            ),
        )


@dataclass(frozen=True)
class BossPageContract:
    """BossPageContract（BOSS 页面契约）冻结官方页面、登录标识和岗位字段定位器。"""

    contract_version: str = "boss-web-v1"  # 当前 BOSS 页面字段契约版本
    allowed_hosts: frozenset[str] = frozenset({"www.zhipin.com"})  # 可导航的官方 HTTPS host
    search_url_template: str = "https://www.zhipin.com/web/geek/job"  # 岗位搜索页面 URL
    detail_url_template: str = "https://www.zhipin.com/job_detail/{security_id}.html"  # 岗位详情 URL
    login_markers: tuple[str, ...] = (
        "css:.login-register",
        "css:.btn-login",
        "text:登录/注册",
    )  # 需要用户登录的页面标识
    verification_markers: tuple[str, ...] = (
        "css:.geetest_panel",
        "css:.captcha-container",
        "text:安全验证",
        "text:请完成验证",
    )  # 需要用户手工完成验证码或安全验证的标识
    full_time_filter: PageField = PageField(
        "full_time_filter",
        ("css:[ka='sel-job-type-1']", "text:全职"),
    )  # 全职岗位筛选器
    job_list: PageField = PageField(
        "job_list",
        ("css:.job-list-box", "css:.job-card-wrapper"),
    )  # 岗位搜索结果列表
    job_card: PageField = PageField(
        "job_card",
        ("css:.job-card-wrapper", "css:li.job-card-wrapper"),
    )  # 单个岗位卡片
    detail_title: PageField = PageField(
        "detail_title",
        ("css:.job-title", "css:h1"),
    )  # 岗位标题
    detail_salary: PageField = PageField(
        "detail_salary",
        ("css:.salary", "css:.job-banner .salary"),
    )  # 月薪范围文本
    detail_city: PageField = PageField(
        "detail_city",
        ("css:.text-city", "css:.job-primary .text-desc"),
    )  # 岗位城市
    detail_experience: PageField = PageField(
        "detail_experience",
        ("css:.job-primary .text-desc", "xpath://span[contains(text(),'年')]"),
    )  # 工作经验要求
    detail_education: PageField = PageField(
        "detail_education",
        ("xpath://span[contains(text(),'本科') or contains(text(),'大专')]",),
    )  # 学历要求
    recruiter_activity: PageField = PageField(
        "recruiter_activity",
        ("css:.boss-active-time", "css:.boss-info-attr"),
    )  # 招聘者活跃度
    company_name: PageField = PageField(
        "company_name",
        ("css:.company-info a", "css:.sider-company .company-info"),
    )  # 公司名称
    company_industry: PageField = PageField(
        "company_industry",
        ("css:.company-info p", "css:.sider-company p"),
    )  # 公司行业
    company_size: PageField = PageField(
        "company_size",
        ("xpath://p[contains(text(),'人') or contains(text(),'以上')]",),
    )  # 公司规模
    job_description: PageField = PageField(
        "job_description",
        ("css:.job-sec-text", "css:.job-detail-section .text"),
    )  # 临时交给受限提取模型的完整 JD 正文区域

    def build_search_url(self, keyword: str, city_code: str) -> str:
        """根据冻结关键词和城市编码生成官方 BOSS 全职搜索 URL。"""
        query = urlencode(
            {
                "query": keyword,
                "city": city_code,
                "jobType": "1901",
            }
        )
        return f"{self.search_url_template}?{query}"

    def build_detail_url(self, security_id: str) -> str:
        """根据 BOSS 页面提供的安全岗位编号生成官方详情 URL。"""
        safe_id = quote(security_id, safe="")
        return self.detail_url_template.format(security_id=safe_id)

    def user_action_required(self, page: Any) -> bool:
        """检测登录或验证码标识；系统只暂停，不输入密码、短信码或验证码。"""
        return _page_has_any(page, (*self.login_markers, *self.verification_markers))

    def read_required(self, page: Any, field: PageField, *, stage: str) -> Any:
        """读取关键字段；所有候选定位器失败时抛出带契约信息的 page_changed。"""
        element = _first_element(page, field.locators)
        if element is None:
            raise PageChangedError(self.contract_version, stage, field.field_name)
        return element


@dataclass(frozen=True)
class TrendsPageContract:
    """TrendsPageContract（搜索关注度页面契约）冻结官方页面与比较卡片定位器。"""

    contract_version: str = "google-trends-web-v1"  # 当前搜索关注度页面字段契约版本
    allowed_hosts: frozenset[str] = frozenset({"trends.google.com"})  # 可导航的官方 HTTPS host
    explore_url_template: str = "https://trends.google.com/trends/explore"  # 搜索关注度探索页 URL
    login_markers: tuple[str, ...] = (
        "text:Sign in",
        "text:登录",
    )  # Google 要求用户登录时的页面标识
    verification_markers: tuple[str, ...] = (
        "text:Verify it's you",
        "text:验证您的身份",
        "text:异常流量",
    )  # Google 验证或异常流量页面标识
    geo_filter: PageField = PageField(
        "geo_filter",
        ("css:[aria-label*='地区']", "css:[aria-label*='Region']"),
    )  # 中国地区筛选器
    time_filter: PageField = PageField(
        "time_filter",
        ("css:[aria-label*='时间']", "css:[aria-label*='Time']"),
    )  # 一年或三个月时间筛选器
    interest_over_time_region: PageField = PageField(
        "interest_over_time_region",
        ("css:.fe-line-chart", "xpath://*[*[contains(text(),'热度随时间变化')]]"),
    )  # 热度随时间变化区域，不用于读取折线点位
    comparison_card: PageField = PageField(
        "comparison_card",
        ("css:.comparison-card", "css:[data-entity='comparison']"),
    )  # 页面直接展示的窗口比较卡片
    comparison_direction: PageField = PageField(
        "comparison_direction",
        ("css:.comparison-card .direction", "css:.comparison-card .trend"),
    )  # 比较卡片显示的上升、下降或持平方向
    comparison_percentage: PageField = PageField(
        "comparison_percentage",
        ("css:.comparison-card .percent", "css:.comparison-card [data-value]"),
    )  # 比较卡片直接显示的变化百分比
    comparison_label: PageField = PageField(
        "comparison_label",
        ("css:.comparison-card .label", "css:.comparison-card .comparison-label"),
    )  # 比较卡片的窗口口径标签
    no_data_marker: PageField = PageField(
        "no_data_marker",
        ("text:没有足够的数据", "text:Not enough data"),
    )  # 页面正常但当前关键词无数据的标识

    def build_explore_url(self, query: str, time_range: str) -> str:
        """生成固定中国地区与明确时间窗口的 Google Trends 官方 URL。"""
        date_value = "today 12-m" if time_range == "past_12_months" else "today 3-m"
        params = urlencode({"q": query, "date": date_value, "geo": "CN"})
        return f"{self.explore_url_template}?{params}"

    def user_action_required(self, page: Any) -> bool:
        """检测 Google 登录或验证标识；系统只暂停等待用户手工处理。"""
        return _page_has_any(page, (*self.login_markers, *self.verification_markers))

    def read_required(self, page: Any, field: PageField, *, stage: str) -> Any:
        """读取关键字段；失败时抛出带契约版本、阶段和字段名的 page_changed。"""
        element = _first_element(page, field.locators)
        if element is None:
            raise PageChangedError(self.contract_version, stage, field.field_name)
        return element


def validate_external_url(url: str, allowed_hosts: frozenset[str] | set[str]) -> str:
    """校验外部 URL 只使用官方 HTTPS host，并拒绝本地地址、短链和危险协议。"""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("external URL is required")
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() != "https":
        raise ValueError("external URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("external URL cannot contain user information")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise ValueError("local host is not allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP address URLs are not allowed")
    if host in _SHORT_LINK_HOSTS:
        raise ValueError("short-link hosts are not allowed")
    normalized_hosts = {item.rstrip(".").lower() for item in allowed_hosts}
    if host not in normalized_hosts:
        raise ValueError("external URL host is not in the official allowlist")
    if parsed.port not in (None, 443):
        raise ValueError("external URL port is not allowed")
    return url.strip()


def _first_element(page: Any, locators: tuple[str, ...]) -> Any | None:
    """按顺序尝试定位器，忽略单个定位失败但不读取 DOM 或保存失败截图。"""
    for locator in locators:
        try:
            element = page.ele(locator, timeout=0.2)
        except Exception:
            continue
        if element:
            return element
    return None


def _page_has_any(page: Any, locators: tuple[str, ...]) -> bool:
    """判断页面是否命中任一登录或验证标识，不返回标识附近的页面原文。"""
    return _first_element(page, locators) is not None
