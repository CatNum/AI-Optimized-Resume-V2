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
  if (!sessionId || (!plan && !snapshot && !data?.active_summary)) return null;

  return (
    <section className="market-research-card" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold text-cyan-100">市场调研</h2>
        {snapshot ? (
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
          <p>阶段：{snapshot.stage}；方向：{snapshot.direction_name || "准备中"}；关键词/城市：{snapshot.keyword || "-"} / {snapshot.city || "-"}</p>
          <p>候选 {snapshot.candidate_count} · 有效岗位 {snapshot.valid_job_count} · 语义分析 {snapshot.semantic_analyzed_count} · 有效耗时 {Math.round(snapshot.elapsed_seconds)} 秒</p>
          {snapshot.error ? <p className="text-amber-200">{snapshot.error.error_code}：{snapshot.error.user_action}</p> : null}
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

      {data?.active_retry ? (
        <div className="mt-3 space-y-2 rounded border border-violet-800/60 bg-violet-950/20 p-3 text-sm text-slate-300">
          <p>方向重试：{data.active_retry.direction_name} · {STATUS_LABELS[data.active_retry.status] || data.active_retry.status} · 阶段 {data.active_retry.stage}</p>
          <p>关键词/城市 {data.active_retry.keyword || "-"} / {data.active_retry.city || "-"} · 候选 {data.active_retry.candidate_count} · 有效 {data.active_retry.valid_job_count} · 语义 {data.active_retry.semantic_analyzed_count} · 有效耗时 {Math.round(data.active_retry.elapsed_seconds)} 秒</p>
          {data.active_retry.error ? <p className="text-amber-200">{data.active_retry.error.error_code}：{data.active_retry.error.user_action}</p> : null}
          <div className="flex gap-2">
            {data.active_retry.available_actions.includes("continue") ? <button className="market-button" disabled={busy} onClick={() => void run(() => continueMarketResearch(data.active_retry!.retry_id, sessionId))}>已完成验证，继续重试</button> : null}
            {data.active_retry.available_actions.includes("cancel") ? <button className="market-button-secondary" disabled={busy} onClick={() => void run(() => cancelMarketResearch(data.active_retry!.retry_id, sessionId))}>取消重试</button> : null}
          </div>
        </div>
      ) : null}
      {error ? <p className="mt-2 text-xs text-rose-300">操作失败：{error}</p> : null}
    </section>
  );
}
