export type ContextUsage = {
  message_count: number;
  max_messages: number;
  token_count: number;
  max_tokens: number;
  usage_ratio: number;
  trimmed?: boolean;
  recommend_new_session?: boolean;
};

/** 展示精度 10%：4/40 → 10%，无小数点 */
export function usageDisplayPercent(usage: ContextUsage): number {
  const messageRatio = usage.message_count / usage.max_messages;
  const tokenRatio = usage.token_count / usage.max_tokens;
  const ratio = Math.max(messageRatio, tokenRatio, usage.usage_ratio ?? 0);
  return Math.min(100, Math.round((ratio * 100) / 10) * 10);
}

export function contextUsageTooltip(usage: ContextUsage): string {
  return `上下文 token：${usage.token_count}/${usage.max_tokens}；消息：${usage.message_count}/${usage.max_messages}`;
}
