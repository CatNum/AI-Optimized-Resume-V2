import { type ContextUsage, usageDisplayPercent } from "../lib/contextUsage";

type Props = {
  usage: ContextUsage | null;
};

export function ContextUsageIndicator({ usage }: Props) {
  if (!usage) return null;

  const percent = usageDisplayPercent(usage);
  const warn = usage.recommend_new_session || usage.trimmed;
  const tokenCount = usage.token_count ?? 0;
  const maxTokens = usage.max_tokens ?? 12000;

  return (
    <span className="relative inline-flex group">
      <span
        className={`cursor-help rounded px-2 py-0.5 text-xs tabular-nums ${
          warn
            ? "border border-amber-700/50 bg-amber-950/40 text-amber-200"
            : "border border-slate-700 bg-slate-900/60 text-slate-400"
        }`}
        aria-describedby="context-usage-tooltip"
      >
        上下文 {percent}%
      </span>
      <span
        id="context-usage-tooltip"
        role="tooltip"
        className="pointer-events-none absolute right-0 top-[calc(100%+6px)] z-50 hidden min-w-[9rem] rounded-md border border-slate-600 bg-slate-900 px-2.5 py-2 text-xs text-slate-200 shadow-lg group-hover:block"
      >
        <span className="block tabular-nums whitespace-nowrap">
          Token：{tokenCount}/{maxTokens}
        </span>
      </span>
    </span>
  );
}
