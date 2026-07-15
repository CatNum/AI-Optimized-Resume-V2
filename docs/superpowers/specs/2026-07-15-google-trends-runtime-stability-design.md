# Google Trends 运行稳定性修复规格

| 属性 | 内容 |
|------|------|
| 状态 | **核心实现与定向测试已完成；真实 Trends → BOSS 主路径待重新人工验收** |
| 版本 | **1.1.0** |
| 日期 | 2026-07-15 |
| 关联规格 | `2026-07-14-market-research-boss-trends-design.md` |
| 实施范围 | 专用 Chrome Profile、Trends 人工介入判断、429 退避重试 |

---

## 1. 背景与现场证据

真实 Google Trends 人工验收暴露出三个互相关联的运行问题：

1. `DedicatedChromeSession`（专用 Chrome 会话）先设置项目 Profile，随后调用 `auto_port(True)`。DrissionPage 最终使用系统临时目录 `DrissionPage/autoPortData/<port>`，没有使用项目的 `market_research/browser_profile`，导致 Google 与 BOSS 登录状态无法跨运行复用。
2. `TrendsPageContract.login_markers`（Trends 登录标记集合）包含页面顶部长期存在的普通“登录 / Sign in”按钮。`user_action_required()`（判断页面是否必须人工介入）因此把可匿名使用的 Trends 页面误判为登录阻断，任务停在 `waiting_user`。
3. 同一 Trends 页面刷新时，`multiline`（热度折线）、`comparedgeo`（地区比较）和 `relatedsearches`（相关搜索）接口出现 HTTP 429。页面显示“糟糕！出了点问题，请稍后重试”，但稍后自动恢复。当前采集器没有识别该技术错误，也没有在重试之间等待，立即重试会加重限流。

本规格只修复以上三项。关键词逗号拆分、使用日常 Chrome Profile、Google Trends 数据口径调整和 BOSS 页面契约不在本次范围。

## 2. 目标

- 专用 Chrome 使用当前 demo 下持久化且独立的 `browser_profile`，关闭后保留登录状态。
- 未登录 Trends 首页的普通登录按钮不触发 `waiting_user`；只有身份验证、异常流量或验证码等真实阻断才暂停。
- Trends 页面出现 429 对应错误文案时，系统执行受预算约束的指数退避，不要求用户点击“继续”。
- 三次退避仍失败时，方向以结构化技术错误结束，不无限刷新、不无限等待用户。

## 3. 非目标

- 不接管用户正在使用的日常 Chrome Profile。
- 不自动输入 Google/BOSS 密码、短信码或验证码。
- 不绕过 Google 的限流、反自动化或安全验证。
- 不引入代理池、账号池、分布式采集或隐藏浏览器。
- 不改变单方向 600 秒有效预算。

## 4. 设计

### 4.1 持久化独立 Profile

`DedicatedChromeSession.open(research_id)`（打开指定调研的专用 Chrome）必须同时满足：

- 使用本机已配置的 Google Chrome 可执行文件。
- 为本次浏览器选择一个当前可用的本地调试端口。
- 通过 `set_local_port(port)` 设置调试端口。
- 通过 `set_user_data_path(profile_dir)` 设置当前 demo 的持久化 Profile。
- 禁止再调用 `auto_port(True)`，因为它会创建并清理临时用户目录。
- 同一 demo 继续维持单活动调研约束；不同 demo 的 Profile 目录保持隔离。
- demo 清理仍可删除该 demo 的 Profile，但普通调研结束不得删除 Profile。

端口选择封装为可注入函数，以便行为测试使用固定端口。端口只用于本机 Chrome DevTools 通信，不写入业务结果或方案快照。

### 4.2 人工介入边界

`TrendsPageContract.user_action_required(page)` 只识别以下真实阻断：

- “Verify it's you / 验证您的身份”；
- “Unusual traffic / 异常流量”；
- 明确 CAPTCHA、安全验证容器或验证文案。

普通“登录 / Sign in”按钮不是阻断标记。Google Trends 可匿名访问时，采集器必须继续执行。用户若希望复用账号相关语言和地区界面，应在持久化专用 Profile 中手工登录一次。

### 4.3 429 页面错误和退避

`TrendsPageContract.technical_retry_required(page)`（判断页面是否出现可重试技术错误）识别：

- “糟糕！出了点问题”；
- “请稍后重试”；
- “Oops! Something went wrong”；
- “Please try again later”。

`GoogleTrendsCollector._collect_once()`（单次 Trends 页面采集）在读取业务字段前检查该状态；命中时抛出 `execution_failed`，诊断消息固定为 `trends_rate_limited`，不得保存页面原文。

`GoogleTrendsCollector._collect_with_retry()`（带重试的 Trends 采集）执行首次请求加三次重试，基础等待依次为 10、30、60 秒。每次等待乘以 0.8～1.2 的随机抖动因子，避免固定频率重复请求。等待使用可注入 `sleep` 和随机因子，便于测试。

退避等待属于自动网页操作时间，计入当前方向的 600 秒 `ActiveBudget`（有效预算时钟）：

- 等待前重新读取 `remaining_seconds()`（剩余有效预算秒数）；
- 剩余预算不足以完成本次等待时，直接返回 `budget_exhausted`；
- 人工验证等待仍按既有规则暂停预算，两者不得混用。

无数据和没有比较卡片仍是正常观察状态，不进入 429 退避。

## 5. 测试接缝

### 5.1 `DedicatedChromeSession.open()`

通过可注入 options、browser、port 和进程工厂启动 Fake Chrome，验证最终配置包含固定本地端口和当前 demo 的 `browser_profile`，且未开启自动端口临时环境。

### 5.2 `TrendsPageContract.user_action_required()`

使用 Fake Page 验证：

- 只有普通“登录”按钮时返回 `False`；
- 出现“验证您的身份”或“异常流量”时返回 `True`。

### 5.3 `GoogleTrendsCollector.collect()`

使用公开 `collect()` 接口、Fake Page、Fake Budget 和注入时钟验证：

- 前三次页面显示技术错误、第四次成功时，等待顺序为 10、30、60 秒；
- 等待计入预算，预算不足时不执行超预算 sleep；
- 三次重试后仍错误时返回结构化 `execution_failed`；
- 普通登录按钮不进入用户等待回调。

## 6. 验收标准

- Chrome 实际启动参数中的 `--user-data-dir` 指向当前 demo 的 `market_research/browser_profile`，不再指向 `DrissionPage/autoPortData`。
- 专用 Chrome 登录 Google 后关闭并重新调研，登录状态仍存在。
- 未登录但没有验证挑战的 Trends 页面不会进入 `waiting_user`。
- 现场出现“出了点问题”时状态保持 `running/collecting_trends`，按退避节奏自动重试。
- 页面恢复后完成 Trends 采集并自动进入 `collecting_boss`。
- 持续 429 时在预算或重试耗尽后形成结构化失败，不无限等待。
- 定向测试、后端完整测试、后端编译和前端生产构建全部通过。

## 7. 实施顺序

1. 修复专用 Chrome 端口与持久化 Profile 组合。
2. 收紧 Trends 人工介入标记。
3. 增加 Trends 技术错误识别和 10/30/60 秒退避。
4. 运行自动化验证和真实页面人工验收。

## 8. 2026-07-15 实施记录

- 三个公开接缝共新增 18 个定向测试，全部通过。
- 后端 `compileall` 和前端生产构建通过。
- 真实 Chrome 启动 smoke 显示 `--user-data-dir` 已指向隔离 demo 的 `market_research/browser_profile`，不再使用 `DrissionPage/autoPortData`。
- 后端完整测试首次在已删除模块 `browser_fetch` 的残留测试处收集失败；排除该文件后结果为 312 通过、25 失败、4 跳过。失败集中在本功能落地前的旧 `prior_results.market`、旧 Worker 顺序、旧 Prompt 与旧空 artifacts 断言，不属于本规格三个修改项，本次不扩大范围修复。
- “完整后端测试全部通过”和真实 Trends → BOSS 主路径仍未满足，因此本规格不标记为全部验收完成。
