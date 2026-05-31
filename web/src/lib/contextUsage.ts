export type ContextUsage = {
  message_count: number;
  max_messages: number;
  token_count: number;
  max_tokens: number;
  usage_ratio: number;
  trimmed?: boolean;
  recommend_new_session?: boolean;
  session_activity?: import("./sessionActivity").SessionActivity;
};

/** 按后端 usage_ratio（纯 token 口径）展示整数百分比 */
export function usageDisplayPercent(usage: ContextUsage): number {
  const ratio =
    usage.usage_ratio ??
    (usage.max_tokens > 0 ? usage.token_count / usage.max_tokens : 0);
  return Math.min(100, Math.round(ratio * 100));
}
