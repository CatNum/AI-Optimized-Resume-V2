# 市场调研 Tool（`market_research`）

## 1. 能力边界

`market_research` 是 market Worker 唯一外部业务工具。它只接收 `plan_id`（冻结方案编号），由 Harness 注入当前 `session_id`（会话编号），再调用进程内唯一 `MarketResearchService`（市场调研服务）异步启动任务。

工具不接受搜索词、城市、action、任意 URL、简历或用户画像。Opportunity Worker 没有浏览器和市场采集权限。

## 2. 参数契约

```json
{
  "type": "object",
  "properties": {
    "plan_id": {"type": "string", "pattern": "^plan_[0-9a-f]+$"}
  },
  "required": ["plan_id"],
  "additionalProperties": false
}
```

`plan_id` 表示用户已经预览并明确确认的完整市场调研方案。Service 在同一临界区内检查 demo 单任务锁、写入 `queued` 状态和任务归属、复核方案哈希并一次性消费方案。

## 3. 异步返回

启动成功返回 `accepted=true`、`research_id`（调研编号）、`plan_id`、初始 `status=queued` 和简短消息。ReAct Runner 收到后立即结束本轮并返回 `status=accepted_async`；该状态只表示后台任务已接受，不表示市场调研完成。

Coordinator 只保存活动调研引用并停止本轮派工，不写 `prior_results.market`，不推进到 JD 分析阶段。

## 4. 下游门禁

市场结果正式发布后，Session 只保存 `result_ref` 或 `reuse_ref`。Harness 每次委托 Opportunity 或后续 pipeline Worker 时重新验证：

- 活动任务已经结束；
- 正式结果目录和版本仍存在；
- 结果未过期；
- `market_result_confirmed=true`；
- `confirmed_result_ref` 与当前唯一引用完全一致。

校验通过后，Harness 才把删除岗位编号、审计引用、截图和内部运行字段的精简结果写入 `context.market_research_result`。旧 `prior_results.market` 只是不可验证历史数据，不能授权、路由或注入上下文。
