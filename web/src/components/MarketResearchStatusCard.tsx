import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelMarketResearch,
  confirmMarketResearchPlan,
  confirmMarketResearchResult,
  continueMarketResearch,
  deleteMarketResult,
  getMarketResearchStatus,
  getMarketReuseCandidates,
  inspectMarketResultDeletion,
  reviseMarketResearchPlan,
  retryMarketDirection,
  reuseMarketResearchResult,
  type DirectionPlan,
  type MarketResearchStatusResponse,
  type ReuseCandidate,
} from "../lib/marketResearchApi";

const ACTIVE = new Set(["queued", "running", "waiting_user", "cancelling"]);
const TERMINAL = new Set(["completed", "partial_completed", "failed", "cancelled"]);

const STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "调研中",
  waiting_user: "等待登录或验证",
  cancelling: "正在取消",
  completed: "已完成",
  partial_completed: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

const REJECTION_LABELS: Record<string, string> = {
  not_full_time: "非全职",
  salary_unparseable: "薪资无法解析",
  recruiter_inactive: "招聘者活跃度不符合要求",
  description_insufficient: "职位描述不足",
  closed_or_offline: "职位已关闭或下线",
  duplicate: "重复岗位",
  company_limited: "同公司岗位数超限",
};

const SYNTHESIS_RULE_LABELS: Record<string, string> = {
  unknown_statistic_ref: "引用了未知统计字段",
  duplicate_statistic_ref: "统计字段重复引用",
  career_definition_missing: "职业定义与岗位引用不一致",
  career_definition_invalid_refs: "职业定义未引用三个有效岗位",
  unknown_skill_explanation_ref: "技能说明引用了未知技能",
  trend_boundary_missing: "缺少 Trends 数据边界说明",
  theme_support_count_mismatch: "主题支持岗位计数不一致",
  theme_unknown_job_ref: "主题引用了未知语义岗位",
  theme_representative_outside_support: "主题代表岗位不在支持集合中",
  prohibited_inference: "出现禁止的比较或推荐性推断",
  numeric_copy: "说明文本重复了冻结统计数字",
  schema_validation: "综合输出结构不符合契约",
  type_error: "综合输出类型不符合契约",
  unknown_rule: "未分类的综合校验规则",
};

const SEMANTIC_FAILURE_LABELS: Record<string, string> = {
  top_level_invalid: "模型返回结构无效",
  missing_output: "缺少岗位输出",
  duplicate_output: "岗位输出重复",
  schema_validation: "岗位字段校验失败",
  evidence_not_found: "依据未在职位描述中找到",
};

type Props = {
  sessionId: string | null;
  refreshTrigger?: number;
  onLockChange: (locked: boolean) => void;
  onTerminal: () => void;
  onStartConfirmedPlan: () => Promise<void>;
};

function csv(value: string[]): string {
  return value.join("、");
}

function splitCsv(value: string): string[] {
  return value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
}

export function MarketResearchStatusCard({
  sessionId,
  refreshTrigger = 0,
  onLockChange,
  onTerminal,
  onStartConfirmedPlan,
}: Props) {
  const [data, setData] = useState<MarketResearchStatusResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftDirections, setDraftDirections] = useState<DirectionPlan[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reuseCandidates, setReuseCandidates] = useState<Record<string, ReuseCandidate[]>>({});
  const [collapsedTerminalKey, setCollapsedTerminalKey] = useState<string | null>(null);
  // notifiedTerminalKeysRef（已通知终态键集合）记录当前 Session 已处理过的调研或重试终态，
  // 避免普通数据刷新把同一个 failed/completed 再次通知给父组件。
  const notifiedTerminalKeysRef = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setData(null);
      return;
    }
    try {
      const next = await getMarketResearchStatus(sessionId);
      setData(next);
      setError(null);
      if (!editing && next.plan) setDraftDirections(next.plan.directions);
      const terminalKeys: string[] = [];
      const snapshot = next.snapshot;
      if (snapshot && TERMINAL.has(snapshot.status)) {
        terminalKeys.push(`research:${snapshot.research_id}:${snapshot.status}`);
      }
      const activeRetry = next.active_retry;
      if (activeRetry && TERMINAL.has(activeRetry.status)) {
        terminalKeys.push(`retry:${activeRetry.retry_id}:${activeRetry.status}`);
      }
      const hasNewTerminal = terminalKeys.some(
        (key) => !notifiedTerminalKeysRef.current.has(key),
      );
      terminalKeys.forEach((key) => notifiedTerminalKeysRef.current.add(key));
      if (hasNewTerminal) {
        onTerminal();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "market_status_failed");
    }
  }, [editing, onTerminal, sessionId]);

  useEffect(() => {
    notifiedTerminalKeysRef.current.clear();
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [sessionId, refresh, refreshTrigger]);

  useEffect(() => {
    if (!sessionId || !data?.plan || data.reuse_selection || data.snapshot) {
      setReuseCandidates({});
      return;
    }
    let cancelled = false;
    void Promise.all(
      data.plan.directions.map(async (direction) => {
        const response = await getMarketReuseCandidates(sessionId, direction.direction_key);
        return [direction.direction_key, response.candidates] as const;
      }),
    ).then((rows) => {
      if (!cancelled) setReuseCandidates(Object.fromEntries(rows));
    }).catch(() => {
      if (!cancelled) setReuseCandidates({});
    });
    return () => { cancelled = true; };
  }, [data?.plan, data?.reuse_selection, data?.snapshot, sessionId]);

  const locked = Boolean(
    (data?.snapshot && ACTIVE.has(data.snapshot.status))
    || (data?.active_retry && ACTIVE.has(data.active_retry.status)),
  );
  useEffect(() => onLockChange(locked), [locked, onLockChange]);

  useEffect(() => {
    if (!locked) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [locked, refresh]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "market_action_failed");
    } finally {
      setBusy(false);
    }
  }

  async function deleteWithReferenceConfirmation(researchId: string) {
    if (!sessionId) return;
    await run(async () => {
      const preview = await inspectMarketResultDeletion(researchId, sessionId);
      const references = preview.referencing_sessions.join("、") || "无 Session";
      if (!window.confirm(`该结果当前被以下 Session 引用：${references}\n确认删除全部正式版本及审计数据吗？`)) return;
      await deleteMarketResult(researchId, sessionId);
    });
  }

  const plan = data?.plan;
  const snapshot = data?.snapshot;
  const activeRetry = data?.active_retry;
  const retryInProgress = Boolean(activeRetry && ACTIVE.has(activeRetry.status));
  const terminalCardKey = activeRetry && TERMINAL.has(activeRetry.status)
    ? `retry:${activeRetry.retry_id}:${activeRetry.status}`
    : snapshot && TERMINAL.has(snapshot.status)
      ? `research:${snapshot.research_id}:${snapshot.status}`
      : null;
  useEffect(() => {
    if (terminalCardKey) {
      setCollapsedTerminalKey(terminalCardKey);
    } else {
      setCollapsedTerminalKey(null);
    }
  }, [terminalCardKey]);
  if (!sessionId || (!plan && !snapshot && !data?.active_summary)) return null;

  if (terminalCardKey && collapsedTerminalKey === terminalCardKey) {
    const terminalLabel = activeRetry && TERMINAL.has(activeRetry.status)
      ? `方向重试${STATUS_LABELS[activeRetry.status] || activeRetry.status}`
      : `市场调研${snapshot ? STATUS_LABELS[snapshot.status] || snapshot.status : "已结束"}`;
    return (
      <div className="mb-2 flex shrink-0 items-center justify-between gap-3 rounded border border-slate-700/70 bg-slate-900/50 px-3 py-2 text-sm text-slate-400">
        <span>{terminalLabel}，详情已收起。</span>
        <button className="text-cyan-300 hover:text-cyan-100" onClick={() => setCollapsedTerminalKey(null)}>查看详情</button>
      </div>
    );
  }

  return (
    <section className="market-research-card" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold text-cyan-100">市场调研</h2>
        {terminalCardKey ? (
          <button className="text-sm text-slate-400 hover:text-slate-200" onClick={() => setCollapsedTerminalKey(terminalCardKey)}>收起</button>
        ) : retryInProgress && activeRetry ? (
          <span className="rounded-full border border-violet-600/70 bg-violet-950/40 px-2 py-0.5 text-xs text-violet-200">
            正在重试 · {activeRetry.stage}
          </span>
        ) : snapshot ? (
          <span className="rounded-full border border-cyan-700/60 px-2 py-0.5 text-xs text-cyan-200">
            {STATUS_LABELS[snapshot.status] || snapshot.status}
          </span>
        ) : null}
      </div>

      {data?.active_summary && !data.owned ? (
        <p className="mt-2 text-sm text-slate-300">已有市场调研正在运行，请等待其结束后再启动。</p>
      ) : null}

      {plan && !snapshot && !data?.reuse_selection ? (
        <div className="mt-3 space-y-3 text-sm">
          <p className="text-slate-300">
            每个方向预算 {plan.budget_seconds} 秒；仅全职岗位；招聘者活跃度限定为
            {plan.filter_policy.allowed_recruiter_activity.join("、")}；月薪上下限必须可解析；
            同一公司最多 {plan.filter_policy.max_jobs_per_company} 个岗位；按 10% 页面截图抽样审计。
          </p>
          {draftDirections.map((direction, index) => (
            <div key={`${direction.direction_key}-${index}`} className="rounded border border-slate-700 p-3">
              {editing ? (
                <div className="grid gap-2 md:grid-cols-2">
                  <input className="market-field" value={direction.direction_name} onChange={(e) => setDraftDirections((rows) => rows.map((row, i) => i === index ? { ...row, direction_name: e.target.value } : row))} />
                  <input className="market-field" value={csv(direction.cities)} onChange={(e) => setDraftDirections((rows) => rows.map((row, i) => i === index ? { ...row, cities: splitCsv(e.target.value) } : row))} />
                  <input className="market-field" value={csv(direction.boss_keywords)} onChange={(e) => setDraftDirections((rows) => rows.map((row, i) => i === index ? { ...row, boss_keywords: splitCsv(e.target.value) } : row))} />
                  <input className="market-field" value={csv(direction.trends_keywords)} onChange={(e) => setDraftDirections((rows) => rows.map((row, i) => i === index ? { ...row, trends_keywords: splitCsv(e.target.value) } : row))} />
                  <label>经验下限 <input className="market-field ml-2 w-20" type="number" value={direction.experience_min} onChange={(e) => setDraftDirections((rows) => rows.map((row, i) => i === index ? { ...row, experience_min: Number(e.target.value) } : row))} /></label>
                  <label>经验上限 <input className="market-field ml-2 w-20" type="number" value={direction.experience_max} onChange={(e) => setDraftDirections((rows) => rows.map((row, i) => i === index ? { ...row, experience_max: Number(e.target.value) } : row))} /></label>
                </div>
              ) : (
                <p><strong>{direction.direction_name}</strong> · 城市 {csv(direction.cities)} · BOSS 词 {csv(direction.boss_keywords)} · 搜索关注度词 {csv(direction.trends_keywords)} · {direction.experience_min}–{direction.experience_max} 年</p>
              )}
            </div>
          ))}
          {Object.entries(reuseCandidates).map(([directionKey, candidates]) =>
            candidates.length > 0 ? (
              <div key={directionKey} className="rounded border border-emerald-800/60 bg-emerald-950/20 p-3">
                <p className="mb-2 text-emerald-200">发现未过期的同方向结果，请选择复用或继续拉取新数据：</p>
                {candidates.slice(0, 3).map((candidate) => (
                  <div key={`${candidate.research_id}:${candidate.result_version}:${candidate.direction_key}`} className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-slate-700/70 pb-2 last:mb-0 last:border-0 last:pb-0">
                    <span>{candidate.direction_name} · {new Date(candidate.researched_at).toLocaleDateString()} · 城市 {csv(candidate.visited_cities)} · 关键词 {csv(candidate.boss_keywords)} · 有效/语义样本 {candidate.valid_job_count}/{candidate.semantic_analyzed_count} · Trends {csv(candidate.trend_time_ranges)} · 到期 {new Date(candidate.expires_at).toLocaleDateString()}</span>
                    <button className="market-button-secondary" disabled={busy} onClick={() => void run(() => reuseMarketResearchResult(sessionId, candidate))}>复用此方向</button>
                  </div>
                ))}
              </div>
            ) : null,
          )}
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <button className="market-button" disabled={busy} onClick={() => void run(async () => { await reviseMarketResearchPlan(plan.plan_id, sessionId, draftDirections); setEditing(false); })}>保存修改</button>
                <button className="market-button-secondary" disabled={busy} onClick={() => { setDraftDirections(plan.directions); setEditing(false); }}>取消修改</button>
              </>
            ) : (
              <button className="market-button-secondary" disabled={busy || plan.status === "consumed"} onClick={() => setEditing(true)}>修改方案</button>
            )}
            {plan.status !== "consumed" ? <button className="market-button" disabled={busy || editing || (data.has_active_research && !data.owned)} onClick={() => void run(async () => { if (plan.status === "draft") await confirmMarketResearchPlan(plan.plan_id, sessionId); await onStartConfirmedPlan(); })}>确认方案并开始调研</button> : null}
          </div>
        </div>
      ) : null}

      {data?.reuse_selection && !snapshot ? (
        <div className="mt-3 space-y-2 text-sm text-slate-300">
          <p>已选择复用方向 {data.reuse_selection.direction_key}，引用结果 {data.reuse_selection.research_id} v{data.reuse_selection.result_version}。数据未复制，有效期保持原值。</p>
          {!data.result_confirmed ? <button className="market-button" disabled={busy} onClick={() => void run(() => confirmMarketResearchResult(data.reuse_selection!.research_id, sessionId))}>确认使用复用结果并继续</button> : <span className="text-emerald-300">复用结果已确认，已进入 JD 分析阶段</span>}
        </div>
      ) : null}

      {snapshot ? (
        <div className="mt-3 space-y-2 text-sm text-slate-300">
          {retryInProgress ? (
            <div className="rounded border border-slate-700/80 bg-slate-950/30 px-3 py-2 text-slate-400">
              <p>上次主调研已结束：{snapshot.error?.error_code || STATUS_LABELS[snapshot.status] || snapshot.status}。</p>
              <p className="mt-1 text-slate-500">当前独立重试正在执行，实时进度以下方紫色状态卡为准。</p>
            </div>
          ) : (
            <>
              <p>阶段：{snapshot.stage}；方向：{snapshot.direction_name || "准备中"}；关键词/城市：{snapshot.keyword || "-"} / {snapshot.city || "-"}</p>
              <p>候选 {snapshot.candidate_count} · 有效岗位 {snapshot.valid_job_count} · 已过滤 {snapshot.rejected_job_count} · 语义有效 {snapshot.semantic_analyzed_count} · 语义未通过 {snapshot.semantic_rejected_job_count} · 有效耗时 {Math.round(snapshot.elapsed_seconds)} 秒</p>
              {Object.keys(snapshot.rejection_counts).length > 0 ? <p className="text-slate-400">过滤原因：{Object.entries(snapshot.rejection_counts).map(([reason, count]) => `${REJECTION_LABELS[reason] || reason} ${count}`).join("；")}</p> : null}
              {snapshot.recent_rejections.length > 0 ? <p className="text-slate-500">最近过滤：{snapshot.recent_rejections.slice(-3).map((audit) => `${audit.title || audit.job_url}（${REJECTION_LABELS[audit.reason] || audit.reason}）`).join("；")}</p> : null}
              {snapshot.synthesis_validation_audits.length > 0 ? <p className="text-amber-200">综合校验：{snapshot.synthesis_validation_audits.map((audit) => `第 ${audit.attempt} 次${SYNTHESIS_RULE_LABELS[audit.rule_code] || audit.rule_code}（${audit.field_paths.join("、")}）`).join("；")}</p> : null}
              {Object.keys(snapshot.semantic_failure_counts).length > 0 ? <p className="text-slate-400">语义未通过原因：{Object.entries(snapshot.semantic_failure_counts).map(([reason, count]) => `${SEMANTIC_FAILURE_LABELS[reason] || reason} ${count}`).join("；")}</p> : null}
              {snapshot.recent_semantic_failures.length > 0 ? <p className="text-slate-500">最近语义未通过：{snapshot.recent_semantic_failures.slice(-3).map((audit) => `${audit.job_url}（${SEMANTIC_FAILURE_LABELS[audit.failure_type] || audit.failure_type}：${audit.field_paths.join("、")}）`).join("；")}</p> : null}
              {snapshot.error ? <p className="text-amber-200">{snapshot.error.error_code}：{snapshot.error.user_action}</p> : null}
            </>
          )}
          <div className="flex gap-2">
            {snapshot.available_actions.includes("continue") ? <button className="market-button" disabled={busy} onClick={() => void run(() => continueMarketResearch(snapshot.research_id, sessionId))}>已完成验证，继续</button> : null}
            {snapshot.available_actions.includes("cancel") ? <button className="market-button-secondary" disabled={busy} onClick={() => void run(() => cancelMarketResearch(snapshot.research_id, sessionId))}>取消调研</button> : null}
            {(snapshot.status === "completed" || snapshot.status === "partial_completed") && !data.result_confirmed ? <button className="market-button" disabled={busy} onClick={() => void run(() => confirmMarketResearchResult(snapshot.research_id, sessionId))}>确认使用结果并继续</button> : null}
            {data.result_confirmed ? <span className="self-center text-emerald-300">结果已确认，已进入 JD 分析阶段</span> : null}
            {TERMINAL.has(snapshot.status) && data.owned && snapshot.completion_published_at ? <button className="market-button-secondary" disabled={busy} onClick={() => void deleteWithReferenceConfirmation(snapshot.research_id)}>删除正式结果</button> : null}
          </div>
          {data.retryable_directions && data.retryable_directions.length > 0 && (!data.active_retry || !ACTIVE.has(data.active_retry.status)) ? (
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-700 pt-2">
              <span>失败方向可独立重试：</span>
              {data.retryable_directions.map((direction) => (
                <button key={direction.direction_key} className="market-button-secondary" disabled={busy || data.has_active_research} onClick={() => void run(() => retryMarketDirection(snapshot.research_id, direction.direction_key, sessionId))}>重试 {direction.direction_name}</button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {activeRetry ? (
        <div className="mt-3 space-y-2 rounded border border-violet-800/60 bg-violet-950/20 p-3 text-sm text-slate-300">
          <p>方向重试：{activeRetry.direction_name} · {STATUS_LABELS[activeRetry.status] || activeRetry.status} · 阶段 {activeRetry.stage}</p>
          <p>关键词/城市 {activeRetry.keyword || "-"} / {activeRetry.city || "-"} · 候选 {activeRetry.candidate_count} · 有效 {activeRetry.valid_job_count} · 已过滤 {activeRetry.rejected_job_count} · 语义有效 {activeRetry.semantic_analyzed_count} · 语义未通过 {activeRetry.semantic_rejected_job_count} · 有效耗时 {Math.round(activeRetry.elapsed_seconds)} 秒</p>
          {Object.keys(activeRetry.rejection_counts).length > 0 ? <p className="text-slate-400">过滤原因：{Object.entries(activeRetry.rejection_counts).map(([reason, count]) => `${REJECTION_LABELS[reason] || reason} ${count}`).join("；")}</p> : null}
          {activeRetry.recent_rejections.length > 0 ? <p className="text-slate-500">最近过滤：{activeRetry.recent_rejections.slice(-3).map((audit) => `${audit.title || audit.job_url}（${REJECTION_LABELS[audit.reason] || audit.reason}）`).join("；")}</p> : null}
          {activeRetry.synthesis_validation_audits.length > 0 ? <p className="text-amber-200">综合校验：{activeRetry.synthesis_validation_audits.map((audit) => `第 ${audit.attempt} 次${SYNTHESIS_RULE_LABELS[audit.rule_code] || audit.rule_code}（${audit.field_paths.join("、")}）`).join("；")}</p> : null}
          {Object.keys(activeRetry.semantic_failure_counts).length > 0 ? <p className="text-slate-400">语义未通过原因：{Object.entries(activeRetry.semantic_failure_counts).map(([reason, count]) => `${SEMANTIC_FAILURE_LABELS[reason] || reason} ${count}`).join("；")}</p> : null}
          {activeRetry.recent_semantic_failures.length > 0 ? <p className="text-slate-500">最近语义未通过：{activeRetry.recent_semantic_failures.slice(-3).map((audit) => `${audit.job_url}（${SEMANTIC_FAILURE_LABELS[audit.failure_type] || audit.failure_type}：${audit.field_paths.join("、")}）`).join("；")}</p> : null}
          {activeRetry.error ? <p className="text-amber-200">{activeRetry.error.error_code}：{activeRetry.error.user_action}</p> : null}
          <div className="flex gap-2">
            {activeRetry.available_actions.includes("continue") ? <button className="market-button" disabled={busy} onClick={() => void run(() => continueMarketResearch(activeRetry.retry_id, sessionId))}>已完成验证，继续重试</button> : null}
            {activeRetry.available_actions.includes("cancel") ? <button className="market-button-secondary" disabled={busy} onClick={() => void run(() => cancelMarketResearch(activeRetry.retry_id, sessionId))}>取消重试</button> : null}
          </div>
        </div>
      ) : null}
      {error ? <p className="mt-2 text-xs text-rose-300">操作失败：{error}</p> : null}
    </section>
  );
}
