import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelMarketResearch,
  confirmMarketResearchPlan,
  confirmMarketResearchResult,
  continueMarketResearch,
  getMarketResearchStatus,
  reviseMarketResearchPlan,
  type DirectionPlan,
  type MarketResearchStatusResponse,
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
  onLockChange,
  onTerminal,
  onStartConfirmedPlan,
}: Props) {
  const [data, setData] = useState<MarketResearchStatusResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftDirections, setDraftDirections] = useState<DirectionPlan[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const terminalKeyRef = useRef<string | null>(null);

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
      const snapshot = next.snapshot;
      if (snapshot && TERMINAL.has(snapshot.status)) {
        const key = `${snapshot.research_id}:${snapshot.status}`;
        if (terminalKeyRef.current !== key) {
          terminalKeyRef.current = key;
          onTerminal();
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "market_status_failed");
    }
  }, [editing, onTerminal, sessionId]);

  useEffect(() => {
    terminalKeyRef.current = null;
    void refresh();
  }, [sessionId, refresh]);

  const locked = Boolean(data?.snapshot && ACTIVE.has(data.snapshot.status));
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

      {plan && !snapshot ? (
        <div className="mt-3 space-y-3 text-sm">
          <p className="text-slate-300">
            每个方向预算 {plan.budget_seconds} 秒；仅全职岗位；招聘者活跃度限定为
            {plan.filter_policy.allowed_recruiter_activity.join("、")}。
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
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <button className="market-button" disabled={busy} onClick={() => void run(async () => { await reviseMarketResearchPlan(plan.plan_id, sessionId, draftDirections); setEditing(false); })}>保存修改</button>
                <button className="market-button-secondary" disabled={busy} onClick={() => { setDraftDirections(plan.directions); setEditing(false); }}>取消修改</button>
              </>
            ) : (
              <button className="market-button-secondary" disabled={busy || plan.status === "consumed"} onClick={() => setEditing(true)}>修改方案</button>
            )}
            {plan.status === "draft" ? <button className="market-button" disabled={busy || editing} onClick={() => void run(() => confirmMarketResearchPlan(plan.plan_id, sessionId))}>确认方案</button> : null}
            {plan.status === "confirmed" ? <button className="market-button" disabled={busy || editing || (data.has_active_research && !data.owned)} onClick={() => void run(onStartConfirmedPlan)}>开始调研</button> : null}
          </div>
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
          </div>
        </div>
      ) : null}
      {error ? <p className="mt-2 text-xs text-rose-300">操作失败：{error}</p> : null}
    </section>
  );
}
