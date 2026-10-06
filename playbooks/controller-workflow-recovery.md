# FLASH CAST 工作流中断恢复手册 V2

## 部门健康恢复

1. 从 Codex 应用核对固定任务的项目 ID、cwd、标题、任务 ID、侧边栏分组和非空可见回复。
2. 健康证明超过 26 小时一律视为 `verification_stale`；只允许使用 `department_health_probe:<department>` 范围的精确健康探针。
3. `read_thread`/`wait_threads` 返回 `completed` 但 messages/items 为空时，只能判定读取结果不完整，不能直接判定部门空回复，更不能把上一次额度失败继续当作本轮错误。先交叉核对同一个固定任务的精确最新轮次：

   ```bash
   python3 tools/flashcast_ops.py department-reply-check \
     --department <department> --turn-id <latest-turn-id> \
     --session-path <exact-local-codex-session.jsonl>
   ```

   此只读命令验证 session/task/cwd、最新 turn、助手最终消息与 task_complete 一致，只输出消息 ID、时间和 SHA-256。不能把其他任务、旧轮次或只有 commentary 的记录当作成功。它不替代 Codex 应用现场的项目、标题、目录和侧边栏验证。
4. 收到并核实回复后运行 `department-health-record`，传入 `--reply-ref`、`--reply-sha256`、`--reply-nonempty`、`--reply-observed-at <original-reply-time>` 和现场身份。原始回复超过 26 小时不得刷新为今天；同一观察重复登记不追加或累加失败。读取渠道仍不一致且无原始回复证据时保持待核实，不伪造失败或健康。
5. 只有当前轮次明确返回额度或瞬时失败时，才登记该轮次的 `failure_class` 和重试提示；不得从历史错误推断当前额度，不得创建项目外替补窗口。

## 派工前阻断恢复

### 侧边栏分组 ID 漂移恢复

侧边栏 ID 是 Codex 应用的运行时标识，不能把旧 ID 与当前现场 ID 的差异直接判成跨项目。总控在读取固定任务现场后按以下顺序处理：

1. 以准确分组名称、项目 ID、固定 task ID、标题和 `cwd` 唯一匹配现场任务；分组名称必须是“装修公司总控”或“装修公司部门”。
2. 仅 `sidebar_section_id` 不同且其余身份全部一致时，记录 `STALE_SIDEBAR_BINDING`，保留旧值和现场新值，更新 `data/department-registry.json` 的对应绑定；不得改变 task ID、项目、标题、目录、角色或健康结论。
3. 由 operations 运行精确健康探针；收到非空可见回复后用 `department-health-record` 写入新的健康记录。过期旧回复不能直接续期。
4. 对已有 `blocked_recovery_required` 的同日或跨日 outbox，写入 `recovery_ready_for_retry`，沿用原 `task_id`、原候选和原依赖；不得新建替补窗口或复制一个新任务掩盖积压。
5. 通过 `policy-check --action-class thread_message` 后，由 operations 向原固定部门发送一次有界补跑包，说明恢复证据、允许范围、剩余工作和不得重复执行的旧步骤；发送后记录 `dispatch_sent`/恢复回执，后续按正常 `chat_ack → outbox_received → QA` 链路继续。
6. 如果现场存在多个同名分组、任务身份有任何不一致、固定窗口不可见或健康探针无非空回复，保持 `blocked`，不得自动修复或绕过门禁。

该分支必须在 operations 的每次计划运行中优先于普通放行和日终汇总；`ACTIVE`、文件存在或旧报告不能代替现场恢复证据。恢复只解决控制层绑定和健康，不代表网站已经发布或业务效果已经改善。

### 发送接口失败

- `list_threads` 可见不等于发送成功。发送工具返回 `isError=true` 或明确错误时，不得继续登记 `dispatch_sent`。必须检查工具业务结果，不能把工具调用完成视为发送成功。
- `notLoaded / thread not found` 可只读核对原固定窗口，并尝试恢复原窗口后安全重试一次；仍失败则停止，不新建替补或换项目。没有新轮次时不能宣称 QA 已启动。
- 已误记 `dispatch_sent`、且其后尚无成功回执时，保存脱敏错误证据，通过 `receipt-record --receipt-type dispatch_failed --department <original-department> --chat-task-id <fixed-id> --supersedes-receipt-id <incorrect-dispatch-id> --replacement-reason thread_not_loaded --evidence <error-file> --idempotency-key <unique-key> --task-id <same-task>` 追加更正。旧记录保留但不再算有效派工；后续成功回执被阻断。
- 恢复仍使用原固定窗口。真正发送成功后登记新的 `dispatch_sent`，沿原恢复点继续，不重做已经交回的内容；不得伪造成功发送来清除阻断。

### 原计划恢复

固定部门恢复健康后，复用原 task_id：

```bash
python3 tools/flashcast_ops.py workflow-repair-plan --task-id <task_id>
python3 tools/flashcast_ops.py workflow-status --task-id <task_id>
```

- `repair_dispatch_plan` 是兼容别名；同一请求重新执行 `dispatch-plan` 也会重新检查可恢复的健康/路由阻断。
- 仅适用于尚无回执的 `planned/blocked/dispatch_ready` 工作流。精确固定部门、项目、cwd、分组、交接及健康仍需有效。
- 恢复只到 `dispatch_ready`，不发送消息，不补造回执、QA、审批或发布。之后正常执行现场路由预检和一次派工。
- 事件中保留原阻断及 plan_refresh；快照丢失，或事件写入后快照写入中断，都由 reconcile 重建。
- 已有派工/QA/执行回执、已终止、证据损坏或模糊任务不能借恢复命令重派。

### 已派工但旧内容窗口被替换、尚无聊天回执

只适用于原工作流仍为 `dispatched`、内容部已有可校验的 `dispatch_sent`，但尚无该部门 `chat_ack`/`outbox_received` 的情况。旧窗口即使有历史非空回复，也不能在注册表已切换后冒充当前固定窗口的回执；不能用 `workflow-repair-plan` 或直接改快照绕过。先核原派工窗口、事件/回执链、旧窗口历史健康事件，以及当前注册表中内容窗口的同项目、同目录、准确分组和**新鲜非空健康事件**。任一项不满足就保持阻断。

门禁全部满足后，运营沿用原 task ID 执行：

```bash
python3 tools/flashcast_ops.py workflow-rebind-department \
  --task-id <original-task-id> --department content-organic-website \
  --old-chat-task-id <original-dispatched-thread-id> \
  --health-event-hash <current-content-health-event-hash>
```

这只追加绑定事件，保留旧 `dispatch_sent`，状态仍为 `dispatched`，**不会**生成聊天或 QA 回执。再核当前固定任务空闲、项目/标题/cwd/分组，运行精确 `policy-check --action-class thread_message`，向当前内容窗口只发送一次有界的原产物复核任务；发送成功后登记新的 `dispatch_sent`。只有新窗口在这次派工后真实产生非空可见回复，才能登记 `chat_ack`，再核原 outbox、学习状态并登记 `outbox_received`，交当前固定 QA。回执工具会拒绝“只换绑、不重新派工”的 `chat_ack`。若当前健康失效、消息发送失败、原证据变化或 QA 尚未完成，不得推进或宣称已发布。

## 全局自动任务路由恢复

1. 独立治理任务运行 `global-routing-audit --shadow`，核对 automation ID、所属项目、目标线程、目标项目和 cwd。
2. shadow 发现错配时只写 `quarantined_pending_owner_approval`，不得自动暂停。
3. 老板批准精确 automation ID 后，使用 Codex 自动化接口暂停；不得直接编辑 `automation.toml`。
4. 修复后再次 shadow，通过后才写 `--record` 总账。总账不保存提示词或聊天正文。

## 目的

在 Codex 任务中断、CLI 重跑、快照丢失或证据变化后，从追加式事件、链式回执和证据哈希恢复项目工作流，不重复分派、不重复消费批准、不重复执行。

## 适用边界

- 只处理本项目的 `logs/`、`data/workflows/` 和证据文件。
- 不连接 Google Ads、GA4、GSC、CMS、CRM、WhatsApp 或生产网站。
- SHA-256 链只用于检测误改；它不是密码学签名或 Codex 全局权限拦截器。
- `paid_promotion_enabled=false` 始终生效，恢复过程不能启用或修改广告。

## 恢复步骤

1. 确认准确 `task_id`，不从文件名猜测或创建新编号。
2. 查看当前状态：

   ```bash
   python3 tools/flashcast_ops.py workflow-status --task-id <task_id>
   ```

3. 运行重建：

   ```bash
   python3 tools/flashcast_ops.py workflow-reconcile --task-id <task_id>
   ```

4. 核对输出的 `current_state`、`missing_receipts`、`blockers` 和 `next_legal_actions`。不要手工把快照状态改到后续阶段。
5. 如果状态是 `blocked_evidence_invalid`，定位 `evidence_missing` 或 `evidence_changed`：
   - 证据丢失：从可核对备份恢复原始证据；无法恢复时保持 blocked，由人工决定取消旧任务并用新 task_id 重建。
   - 证据变更：优先从备份恢复原始字节。若已核实为同一路径上的合法更正或重新生成，不覆盖或改写旧 JSONL；由原部门记录 `evidence_replacement`，精确引用旧 `receipt_id`、全部变化路径、原因代码和新幂等键。旧哈希与变化事实继续留在审计链中。
   - `evidence_replacement` 不能替换缺失文件、无关路径、其他部门证据或另一条替换回执；文件后续再次变化会重新阻断。
   - 持续滚动的总账若已被旧回执作为哈希证据引用，且项目 `backups/` 内有与该回执原始 SHA-256、大小完全一致的不可变版本，由原部门用 `evidence_archive` 指向该回执 ID、原活动路径和备份路径。它只保存历史版本的真实性，不把当前总账当成旧版，也不改变执行/QA/发布结论；封存件变更或缺失仍阻断。新回执优先直接引用任务专属不可变快照，避免反复重定基活动总账。
   - 哈希链错误：保留现场，不手工改写 JSONL，先恢复对应备份或交由人工核对。
6. 如果缺少快照但 `planned` 事件仍在，`workflow-reconcile` 会原子重建 `data/workflows/<task_id>.json`。
7. 如果缺少 `chat_ack`，必须回到原固定部门任务核对非空回复；文件、outbox 或总控转述不能补作聊天回执。
8. 如果批准已是 `consumed` 或 `revoked`，不得重用。新动作或新范围需要新的精确批准。
9. 恢复后再次运行 `workflow-status`，只执行其返回的下一合法动作。

## 子智能体超时和停止恢复

1. 先运行：

   ```bash
   python3 tools/flashcast_ops.py delegation-status --task-id <task_id>
   ```

2. 该命令校验 `logs/delegations/<task_id>.jsonl` 的 SHA-256 链，并把已超过 `deadline_at` 的活动委派幂等地标记为 `timed_out/timeout`。
3. 只有 `failed`、`timed_out` 或 `cancelled` 才可以使用同一 `delegation_id` 进入下一 `attempt`；最多 2 次。
4. 超时或子智能体完成都不改变主工作流状态。固定部门必须在原聊天整合结果，然后正常记录 `chat_ack`/outbox/QA 回执。
5. 链校验失败时保留现场，不手工改 JSONL；从精确备份恢复或由老板决定取消委派。

## 固定部门窗口健康与替补

1. 运行 `python3 tools/flashcast_ops.py department-status`，检查 `reply_health`、`dispatch_eligible`、项目 ID、`cwd`、侧边栏分组和交接文件。
2. 出现 `department_setup_blocked` 或 `blocked_replacement_requires_app_capability` 时先区分真实失败和读取接口遗漏，按上面的原始回复核验处理；不会因为汇总接口空列表就建立替补。
   - 若该窗口有活动自动任务，先使用 `policy-check --action-class automation_update --scope automation_quarantine:<automation-id> --target-automation-status PAUSED` 做精确路由预检；缺少 `PAUSED` 或传入其他状态均拒绝，不允许向不健康窗口发消息或借此改变业务提示词。
3. 从 Codex 应用现场核对原任务、所属项目、标题、`cwd`、分组和最近非空回复。
4. 如需替补，新任务必须进入注册表为该角色指定的分组：运营总控进入“装修公司总控”，执行部门进入“装修公司部门”。首条任务包必须引用原 `handoff_path`、部门 Skill、学习记忆和政策文件。
5. 新任务产生非空可见回复后，再用应用现场状态重新验证。只有全部一致才可更新注册表；不能验证分组时继续 blocked，禁止在项目外建立替补。
6. 切换后保留原 task ID、替换原因、交接路径、健康检查时间和新 task ID；不删除旧窗口证据。
7. 对仍处于 `dispatch_ready` 且尚无任何回执的活动工作流运行 `workflow-refresh-bindings`，把内容部和 QA 等固定任务 ID 刷新到新注册表绑定；已有回执时禁止使用该派工前命令。若恰好是内容部已派工但未回执，按上面的 `dispatched` 窄路径恢复；已有证据或 QA 返工时使用既有 `workflow-rebind-department`/`workflow-rebind-qa` 门禁。其余情况保留原链并人工核对，不擅自新建工作流。

## 历史 V1 任务只读回放

历史任务没有原生回执时，使用 shadow：

```bash
python3 tools/flashcast_ops.py workflow-reconcile \
  --task-id <legacy-task-id> \
  --shadow
```

Shadow 只读取旧 dispatch/outbox/证据，不写入工作流、不补造 QA、不补造审批、不修改历史文件。

## 人工升级条件

出现以下任一情况时停止自动恢复：

- 事件与回执都缺失，无法证明任务身份；
- 固定部门 task ID 与注册表不匹配；
- 替补任务无法验证已进入注册的侧边栏分组，或未继承交接文件；
- 委派账本链断裂、尝试超过 2 次或需要外部动作；
- 证据可能含密码、Token、Cookie、OAuth、私钥或客户 PII；
- 批准内容、动作范围或执行结果无法精确对应；
- 用户要求的动作超出 V1 项目控制层边界。
