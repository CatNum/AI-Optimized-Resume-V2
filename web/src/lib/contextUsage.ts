export type ContextUsage = {
  message_count: number;
  max_messages: number;
  token_count: number;
  max_tokens: number;
  usage_ratio: number;
  trimmed?: boolean;
  recommend_new_session?: boolean;
};

/** 取消息/token 占用率的较大值，四舍五入为整数百分比（2/40 → 5%） */
export function usageDisplayPercent(usage: ContextUsage): number {
  const messageRatio = usage.message_count / usage.max_messages;
  const tokenRatio = usage.token_count / usage.max_tokens;
  const ratio = Math.max(messageRatio, tokenRatio);
  return Math.min(100, Math.round(ratio * 100));
}
