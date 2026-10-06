# 跨部门依赖编排

总控只调度，不代做专业交付。优先使用 `python3 tools/flashcast_ops.py dispatch-plan --request "..." --task-id <id>` 生成含依赖的本地计划。

## 标准执行波次

1. `wave_1`：没有前置依赖的事实/数据/brief 任务；并行发送。
2. `wave_2+`：只有 `depends_on` 的部门已在聊天回复且证据文件存在，才发送。
3. 最后一个专业波次结束后才进入 QA；规划/候选完整性的 QA PASS 不等于发布级 QA PASS，更不等于已上线。
4. `flashcast.com.my` 常规 R1/R2 网站优化在发布级 QA PASS、运营 `AUTO_RELEASE`、精确政策放行、备份与回滚齐全后，按常驻授权走锁定的 CMS 或代码通道，不逐次等待老板批准；R3 与授权外动作才交老板。执行后须公开复核并记录回执。
5. 部门当前轮次为 `active` 时，非紧急后续派工等其完成，再重新核对固定任务现场身份与路由门禁；不得为了跟进而强行插入消息。

## 收益式委派和并发上限

部门波次与部门内子智能体是两层调度：总控只向固定部门窗口派工；固定部门在确认接单后，才可为内部独立子问题调用短生命周期子智能体。

1. 先写明收益：`parallel_latency`、`specialist_capability` 或 `context_isolation`。
2. 相互依赖、同文件/同数据写入、外部动作和跨项目任务必须串行或阻断。
3. 全局最多 3 个，同部门最多 2 个；默认 900 秒超时，上限 1800 秒，最多 2 次尝试。
4. 终止必须记录 `completed`、`task_failed`、`timeout`、`cancelled`、`dependency_blocked`、`policy_blocked` 或 `no_progress`。
5. 子智能体完成只能作为固定部门的内部证据；固定部门必须自己回复、整合、写 outbox 并交 QA。

具体门禁以 `data/delegation-policy.json` 和 `data/task-contract.json#delegation_contract` 为准。

## 常见链路

- Google Ads 审计：付费增长与转化数据 → QA → 老板审核。
- 广告文案/落地页：内容/SEO/网站 → 付费部检查搜索意图和 message match → QA → 老板审核。
- 转化异常：付费部与内容/网站并行取证 → QA；需要业务真值时再交销售确认。
- 获客图片/视频：内容 brief 和付费测试目标（任务缺失时由视觉部列为依赖）→ 视觉设计与视频 → QA → 老板审核。
- 全增长复盘：付费、内容和销售并行 → 视觉按 brief/测试目标制作（若本次需要）→ QA → 总控汇总。

## 完成判定

部门状态必须同时满足：消息发送成功、部门聊天有非空回传、outbox/report 有结构化副本、证据路径可读、需要时有学习事件。缺一项保持 `needs_input` 或 `blocked`。
