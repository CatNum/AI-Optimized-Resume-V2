from __future__ import annotations

from typing import Any

from career_os.platform.market_research.models import (
    DirectionResult,
    MarketResearchResult,
    ReferencedDirectionResult,
    ThemeSummary,
)


class PlainTextMarketReportRenderer:
    """PlainTextMarketReportRenderer（纯文本市场报告渲染器）只拼接已验证文字和冻结数字。"""

    def render(self, result: MarketResearchResult) -> str:
        """按固定八个章节输出普通文本，不生成 Markdown 表格、图表或新推断。"""
        directions = [
            direction
            for direction in result.successful_directions
            if isinstance(direction, DirectionResult)
        ]
        lines: list[str] = ["市场调研结果"]
        lines.extend(self._data_scope(directions, result))
        lines.extend(self._responsibilities(directions))
        lines.extend(self._experience_and_education(directions))
        lines.extend(self._skills(directions))
        lines.extend(self._salary(directions))
        lines.extend(self._trends(directions))
        lines.extend(self._limitations(directions, result))
        lines.extend(self._comparison(result))
        return "\n".join(lines).strip()

    @staticmethod
    def _data_scope(
        directions: list[DirectionResult],
        result: MarketResearchResult,
    ) -> list[str]:
        """渲染方向、实际城市、关键词和两类岗位样本数。"""
        lines = ["", "1. 数据范围"]
        for direction in directions:
            lines.append(
                f"{direction.direction_name}：本次样本数 {direction.valid_job_count}，"
                f"语义有效样本 {direction.semantic_analyzed_count}，"
                f"公司数 {direction.company_count}，样本等级 {direction.sample_level}。"
            )
            lines.append(
                f"实际城市：{'、'.join(direction.visited_cities) or '未记录'}；"
                f"BOSS 关键词：{'、'.join(direction.boss_keywords)}；"
                f"搜索关注度关键词：{'、'.join(direction.trends_keywords)}。"
            )
        if result.failed_directions:
            lines.append(
                "未成功方向："
                + "、".join(direction.direction_name for direction in result.failed_directions)
                + "。"
            )
        return lines

    def _responsibilities(self, directions: list[DirectionResult]) -> list[str]:
        """渲染职业定义和至少两个岗位支持的职责、要求及岗位证据主题。"""
        lines = ["", "2. 当前岗位职责"]
        for direction in directions:
            lines.append(f"{direction.direction_name}：")
            if direction.career_definition:
                lines.append(f"职业定义：{direction.career_definition}")
            lines.extend(self._theme_lines("职责", direction.responsibility_themes))
            lines.extend(self._theme_lines("要求", direction.requirement_themes))
            lines.extend(self._theme_lines("优先条件", direction.preference_themes))
            lines.extend(self._theme_lines("岗位证据", direction.evidence_themes))
        return lines

    @staticmethod
    def _theme_lines(label: str, themes: tuple[ThemeSummary, ...]) -> list[str]:
        """渲染主题支持数和最多三个可追溯代表岗位 URL。"""
        lines: list[str] = []
        for index, theme in enumerate(themes, start=1):
            lines.append(
                f"{label}{index}：{theme.theme}（支持岗位 {len(theme.support_job_ids)}）"
            )
            for reference in theme.representative_jobs:
                lines.append(
                    f"代表岗位：{reference.title}｜{reference.company_name}｜{reference.job_url}"
                )
        if not themes:
            lines.append(f"{label}：重复主题样本不足。")
        return lines

    @staticmethod
    def _experience_and_education(directions: list[DirectionResult]) -> list[str]:
        """渲染冻结经验重点、相邻档位与学历分布。"""
        lines = ["", "3. 经验与学历"]
        for direction in directions:
            experience = direction.experience_analysis
            lines.append(
                f"{direction.direction_name}经验重点："
                f"{'、'.join(experience.get('focus_groups') or ()) or '未形成'}；"
                f"相邻档位：{'、'.join(experience.get('secondary_groups') or ()) or '无'}。"
            )
            lines.append(
                "经验分布：" + _distribution_text(experience.get("distribution") or {}) + "。"
            )
            lines.append(
                "学历分布：" + _distribution_text(direction.education_distribution) + "。"
            )
        return lines

    @staticmethod
    def _skills(directions: list[DirectionResult]) -> list[str]:
        """渲染正式技能与单岗位孤立技能，并明确两类统计分母。"""
        lines = ["", "4. 技能要求"]
        for direction in directions:
            lines.append(f"{direction.direction_name}：")
            for skill in direction.skill_statistics:
                lines.append(
                    f"{skill.canonical_name}：提及 {skill.mention_count}/"
                    f"{skill.mention_denominator}，必需 {skill.required_count}/"
                    f"{skill.semantic_denominator}，优先 {skill.preferred_count}/"
                    f"{skill.semantic_denominator}。"
                )
            if direction.emerging_or_isolated_skills:
                lines.append(
                    "单岗位技能："
                    + "、".join(
                        skill.canonical_name
                        for skill in direction.emerging_or_isolated_skills
                    )
                    + "。"
                )
        return lines

    @staticmethod
    def _salary(directions: list[DirectionResult]) -> list[str]:
        """渲染程序冻结的上下限中位数和观察区间，不输出平均或总包估算。"""
        lines = ["", "5. 薪资"]
        for direction in directions:
            salary = direction.salary_analysis
            lines.append(
                f"{direction.direction_name}：税前人民币月薪下限中位数 "
                f"{salary.get('salary_min_median')} 元，上限中位数 "
                f"{salary.get('salary_max_median')} 元；本次样本观察区间 "
                f"{salary.get('observation_min')}～{salary.get('observation_max')} 元/月。"
            )
            if direction.salary_explanation:
                lines.append(direction.salary_explanation)
        return lines

    @staticmethod
    def _trends(directions: list[DirectionResult]) -> list[str]:
        """渲染 v2 周度计算结果；所有变化均为归一化热度点而非百分比。"""
        lines = ["", "6. Google 搜索关注度"]
        for direction in directions:
            lines.append(f"{direction.direction_name}：")
            trend = direction.trend_result
            if trend.source_status != "success":
                lines.append("来源限制：Google Trends 数据未完整可用，本次不据此作趋势判断。")
            for analysis in trend.keyword_analyses:
                if analysis.annual_change is None or analysis.first_half is None or analysis.second_half is None:
                    lines.append(f"{analysis.keyword}：年度数据不足。")
                    continue
                lines.append(
                    f"{analysis.keyword}：{analysis.first_half.label}（{analysis.first_half.start_date} 至 {analysis.first_half.end_date}）均值 {analysis.first_half.mean:.1f}，"
                    f"{analysis.second_half.label}（{analysis.second_half.start_date} 至 {analysis.second_half.end_date}）均值 {analysis.second_half.mean:.1f}，"
                    f"变化 {analysis.annual_change.delta_points:.1f} 个归一化热度点（{analysis.annual_change.direction}）。"
                )
            if direction.trend_explanation:
                lines.append(direction.trend_explanation)
        lines.append("0 是有效归一化热度值，不代表绝对零次搜索；低搜索量、抽样和噪声可能影响结果。以上为搜索关注度，不代表招聘趋势。")
        return lines

    @staticmethod
    def _limitations(
        directions: list[DirectionResult],
        result: MarketResearchResult,
    ) -> list[str]:
        """渲染默认排序、账号状态、个性化和小样本限制。"""
        lines = ["", "7. 样本限制"]
        limitations = [
            limitation
            for direction in directions
            for limitation in direction.sample_limitations
        ]
        limitations.extend(result.source_boundaries[:2])
        for index, limitation in enumerate(dict.fromkeys(limitations), start=1):
            lines.append(f"{index}）{limitation}")
        return lines

    @staticmethod
    def _comparison(result: MarketResearchResult) -> list[str]:
        """渲染多方向并列说明；单方向明确没有对照。"""
        lines = ["", "8. 职业方向对照"]
        if result.comparison is None:
            lines.append("本次只有一个成功方向，不生成方向对照。")
        else:
            lines.append(result.comparison.summary)
        reused = [
            direction.direction_name
            for direction in result.successful_directions
            if isinstance(direction, ReferencedDirectionResult)
        ]
        if reused:
            lines.append("复用方向：" + "、".join(reused) + "。")
        return lines


def _distribution_text(distribution: dict[str, Any]) -> str:
    """把确定性分类计数转成简洁纯文本，不使用 Markdown 表格。"""
    return "、".join(f"{name} {count}" for name, count in distribution.items()) or "无"
