现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# FLASH CAST 活跃增长运营工具层

`python3 tools/result_handoff_key.py --outbox <最终V2> --json`：只读生成原结果完整身份的确定通知键，避免超过200字符；不入队、不发送、不授予权限。恢复顺序见 `playbooks/result-notification-key-and-recovery.md`。

这是从老 `skill-zhuangxiuseogeo` 迁移并适配到新“装修公司虚拟员工”项目的运营工具层。
第一批负责数据可信度、转化对账、行动编排、交接、质检和 Google Ads 日检；第二批负责内容、SEO、学习复盘、备份回滚和工作区维护。

它把老系统的 Content Studio、SEO 索引审计、学习复盘、备份回滚和工作区维护，统一适配到当前目录结构：

- `data/`：当前输入和结构化证据
- `drafts/`：内容草稿
- `logs/`：运行账本、学习记录、变更记录
- `reports/`：中文报告
- `backups/`：指定文件的备份和回滚依据
- `archive/`：只在人工批准后移动旧产物，不直接删除
- `history/`：老项目历史资料，只读

## 第一批：增长数据和日检

初始化时会建立两个空模板。空模板不是假数据，日检会把它们标记为缺口：

```bash
python3 tools/flashcast_ops.py init
```

如果要把旧 Skill 里已经存在的脱敏 GA4/线索快照整理到新项目，可以运行一次：

```bash
python3 tools/flashcast_ops.py migrate-inputs
```

它只会填充空的 active 表，不会覆盖你已经填写的新数据；迁移行会保留 `source_record`，并在报告中标为历史参考。

检查每个数据源的存在、列名、日期范围和新鲜度。GSC 自然搜索、GA4 自然流量、GA4 咨询动作、Google Ads 转化动作和销售线索均属于核心决策来源；过期核心来源会进入 blocker：

```bash
python3 tools/flashcast_ops.py source-manifest
```

对账 Google Ads、Ads 转化动作、GA4 咨询动作和销售确认的真实线索。工具只使用 GA4 最新 `window_end`，不会把历史窗口与当前窗口相加；Ads 与 GA4 不同窗时会阻断直接比较。Ads 主要转化的追踪状态若为 `Needs attention`、配置错误或未验证，也会进入 blocker，防止重复创建转化或在故障状态下扩量：

```bash
python3 tools/flashcast_ops.py conversion-reconcile
```

生成按 P0/P1/P2 排序的行动队列。P0 只表示必须先处理，不代表自动执行：

```bash
python3 tools/flashcast_ops.py action-queue
```

执行完整的 Google Ads 只读日检环（数据检查 → 转化对账 → 行动队列 → Reality Checker）：

```bash
python3 tools/flashcast_ops.py ads-daily
```

查看 Reality Checker 是否允许进入老板审核：

```bash
python3 tools/flashcast_ops.py qa-gate --scope google-ads-daily
```

记录部门交接。证据写相对路径，不写密码、Token 或 Cookie：

```bash
python3 tools/flashcast_ops.py handoff \
  --task-id ads-daily-current \
  --from-department paid-growth-data \
  --to-department qa \
  --completed "完成 Ads、GA4、销售线索对账" \
  --unfinished "等待负责人确认是否暂停广告系列" \
  --evidence data/leads/conversion-reconciliation.json \
  --cannot-assume "点击不等于线索，导出不等于实时状态" \
  --next-action "审核 P0/P1 行动并给出明确批准或驳回" \
  --owner-approval-required
```

查看所有工具运行记录和输入输出：

```bash
python3 tools/flashcast_ops.py run-ledger
```

第一批生成的关键证据：`data/source-manifest.json`、`data/data-health.json`、`data/leads/conversion-reconciliation.json`、`data/action-queue.csv`、`data/qa-gate.json`、`data/google-ads/ads-daily.json`、`logs/run-ledger.jsonl` 和 `logs/handoffs/`。

默认状态是只读、草稿或等待人工审核。工具不会登录或修改 Google Ads、GA4、GTM、网站、CMS、CRM，也不会自动联系客户。

## 工作流与部门路由控制层 V2

`dispatch-plan` 现在会幂等初始化项目工作流。同一 `task_id + request` 重跑不会重复创建事件；同一任务编号改换内容会被阻止。

路由仅在明确广告语义（如“广告关键词”）时把关键词任务送付费部；单纯“关键词”不能当作付费授权。若旧的 multi 路由误命中、专业部门已有真实回执但误命中的部门**从未收到任何回执**，可审计地保留原始分派计划并收窄路由：

```bash
python3 tools/flashcast_ops.py workflow-correct-route \
  --task-id fc-YYYYMMDD-example \
  --route-id seo-review
```

该命令只保留原始 multi 计划中已命中的一条规则；不得移除有回执的部门、补造聊天回执，或在 QA 裁决/外部执行之后改路由。纠偏追加事件并重建状态，不覆写旧计划和回执。

```bash
python3 tools/flashcast_ops.py dispatch-plan \
  --task-id fc-YYYYMMDD-example \
  --request "老板目标和安全边界"
```

消息发送、非空聊天确认和 outbox 收到后，分别记录回执。路径用分号分隔，回执不保存聊天正文：

```bash
python3 tools/flashcast_ops.py policy-check \
  --task-id fc-YYYYMMDD-example \
  --department operations \
  --action-id dispatch-content-v1 \
  --action-class thread_message \
  --scope department:content-organic-website \
  --source-project-id <LOCAL_PROJECT_ID> \
  --target-project-id <LOCAL_PROJECT_ID> \
  --target-department content-organic-website \
  --target-thread-id <registry-fixed-task-id> \
  --target-thread-title "FLASH CAST｜内容、SEO与网站增长部｜2026-09" \
  --target-cwd "<PROJECT_ROOT>" \
  --target-sidebar-section-id <LOCAL_SIDEBAR_SECTION_ID> \
  --payload-sha256 <task-package-sha256>

python3 tools/flashcast_ops.py receipt-record \
  --task-id fc-YYYYMMDD-example \
  --receipt-type dispatch_sent \
  --department content-organic-website \
  --chat-task-id <registry-fixed-task-id> \
  --policy-decision-id <routing-allow-decision-id> \
  --idempotency-key fc-YYYYMMDD-example-content-dispatch-v1

python3 tools/flashcast_ops.py receipt-record \
  --task-id fc-YYYYMMDD-example \
  --receipt-type chat_ack \
  --department content-organic-website \
  --chat-task-id <registry-fixed-task-id> \
  --ack-nonempty \
  --idempotency-key fc-YYYYMMDD-example-content-ack-v1

python3 tools/flashcast_ops.py receipt-record \
  --task-id fc-YYYYMMDD-example \
  --receipt-type outbox_received \
  --department content-organic-website \
  --evidence logs/department-outbox/fc-YYYYMMDD-example-content.json \
  --idempotency-key fc-YYYYMMDD-example-content-outbox-v1
```

`thread_message`、`automation_create` 和 `automation_update` 都必须提供来源/目标项目、目标部门、固定任务 ID、标题、`cwd`、登记的侧边栏分组 ID 和正文 SHA-256。任一身份不匹配即返回 `blocked_cross_project` 或 `blocked_route_invalid`。路由日志只保存哈希，不保存消息或计划任务提示词正文。公司角色和关联部门数量逐行读取 data/department-registry.json；模糊请求只停在总控补问，不广播给所有部门。

QA 回执只能是 `pass` 或 `blocked`。`pass` 不会自动创建老板批准：

```bash
python3 tools/flashcast_ops.py receipt-record \
  --task-id fc-YYYYMMDD-example \
  --receipt-type qa_verdict \
  --department qa \
  --chat-task-id <registry-fixed-qa-task-id> \
  --verdict pass \
  --evidence reports/YYYY-MM-DD-example-qa.md \
  --idempotency-key fc-YYYYMMDD-example-qa-pass-v1
```

外部执行的批准必须精确到 `task_id + action_id + action_class + scope`，默认单次使用：

```bash
python3 tools/flashcast_ops.py approval-record \
  --task-id fc-YYYYMMDD-example \
  --action-id publish-page-1 \
  --action-class site_publish \
  --scope /zh/services/example \
  --source-message-ref owner-message-reference

python3 tools/flashcast_ops.py policy-check \
  --task-id fc-YYYYMMDD-example \
  --department content-organic-website \
  --action-id publish-page-1 \
  --action-class site_publish \
  --scope /zh/services/example \
  --approval-id <approval-id> \
  --consume-approval
```

`paid_promotion_enabled=false` 是硬门禁；即使有普通批准，`ads_write` 也必须返回 `deny`。装修网站常规优化可使用 `data/action-policy.json` 中的有效常驻授权；scope 必须以 `flashcast.com.my:` 开头。QA 通过后，`policy-check --consume-approval` 会生成并消费一条与本次 `task_id + action_id + action_class + scope` 绑定的单次许可，并在结果中返回 `approval_basis=standing_authorization`、`standing_authorization_id` 和实际 `approval_id`，执行回执必须引用这些字段。购物网站或其他 scope 不会命中。当前控制层只是项目内审计和决策机制，不是密码学签名，也不是 Codex 全局工具中间件。

同一精确发布动作部分完成、`execution_result` 已记录为 `blocked` 后，普通 `policy-check` 仍拒绝重复消费批准。确认上一运行的准确失败阶段、当前 SHA 和证据链后，恢复该**同一动作**可带 `--retry-blocked-execution-receipt-id <最新阻断执行回执 ID>`。仅当工作流保持 `blocked / execution_result_blocked`、原 QA 和已消费的精确批准/政策决定均匹配、回执证据完整时，才签发一次 `approval_basis=blocked_execution_retry` 的恢复许可；同一阻断回执不能签发第二次。它不适用于新 SHA、新 scope、新动作、缺证据或广告硬门禁，也不代替 GitHub 受保护环境审核。若再次失败，先记录新 `execution_result:blocked` 和真实失败证据，再判断下一步；不得盲目重试。

查看或恢复状态：

```bash
python3 tools/flashcast_ops.py workflow-status --task-id fc-YYYYMMDD-example
python3 tools/flashcast_ops.py workflow-reconcile --task-id fc-YYYYMMDD-example
python3 tools/flashcast_ops.py workflow-repair-plan --task-id fc-YYYYMMDD-example
python3 tools/flashcast_ops.py workflow-reconcile --task-id <legacy-task-id> --shadow
```

`workflow-repair-plan`（兼容别名 `repair_dispatch_plan`）重新核对尚无回执的原固定部门计划。健康恢复后只前进至 `dispatch_ready`；未恢复、身份变化、已有回执、终止状态或链损坏均不能借此重派。`dispatch-plan` 同一请求重跑也会刷新可恢复的阻断。plan_refresh 追加进事件，原阻断历史保留，中断和快照丢失后可重建。

当应用读取接口显示 completed 但省略全部消息时，用 `department-reply-check --department <id> --turn-id <latest-turn-id> --session-path <exact-session.jsonl>` 只读校验原始最终回复和 task_complete。仅允许完成记录省略结构完整的末尾记忆引用元数据，正文仍须完全一致。输出不包含聊天正文，仅含身份、原始时间及哈希；仍须独立核对应用中的项目、cwd、标题及分组。不要把读取接口空列表当作部门失败，或沿用旧轮次额度错误。健康登记支持 `--reply-observed-at`，过期回复不能续为当前健康，相同观察重复登记幂等。

派工工具返回 `isError=true` 时禁止登记 `dispatch_sent`。若已经误登记，且没有后续成功回执，用 `receipt-record --receipt-type dispatch_failed` 引用同部门最新错误回执的 `--supersedes-receipt-id`，附脱敏 `--evidence` 与 `--replacement-reason` 原因代码。更正只追加，保留旧记录并阻断后续成功阶段。恢复原固定窗口、再次现场预检且真实发送成功后，登记新 `dispatch_sent` 沿恢复点继续。详情见 `playbooks/controller-workflow-recovery.md`。

`workflow-status` 中 `owner_approval_required` 表示该工作流是否包含老板审批门禁；`owner_approval_pending` 仅在当前阶段已经进入 `waiting_owner_approval` 时为 `true`，不得把尚未到审批阶段误报为不需要审批。

如果既有证据文件在登记后被核实为更正或重新生成，工作流会先降级到 `blocked_evidence_invalid`。不得改写旧 JSONL；由原部门用当前同一路径、旧 `receipt_id` 和原因代码登记显式替换基线，旧哈希仍保留在追加式审计链中：

```bash
python3 tools/flashcast_ops.py receipt-record \
  --task-id fc-YYYYMMDD-example \
  --receipt-type evidence_replacement \
  --department qa \
  --evidence reports/evidence/example/evidence-manifest.json \
  --supersedes-receipt-id <old-receipt-id> \
  --replacement-reason verified_manifest_correction \
  --idempotency-key fc-YYYYMMDD-example-evidence-replacement-v1
```

替换回执必须精确覆盖该旧回执中全部发生变化的路径；无关路径、缺失文件、跨部门替换或再次变化都会继续保持阻断。

对 `data/content/organic-growth-backlog.json` 这类持续更新的总账，优先在**首次登记执行/复核回执之前**用 `backup` 保存任务专属不可变快照，并把快照路径作为回执证据，不要把活动总账当成长期唯一哈希证据。历史回执已经指向活动路径时，原部门可在核对原回执哈希、备份字节和当前总账连续性后，追加 `evidence_archive`。它只证明旧版本被项目内备份保存，不把今天的总账冒充旧状态，也不改变 QA 或发布结论：

```bash
python3 tools/flashcast_ops.py receipt-record \
  --task-id fc-YYYYMMDD-example \
  --receipt-type evidence_archive \
  --department qa \
  --scope data/content/organic-growth-backlog.json \
  --evidence backups/<change-id>/payload/data/content/organic-growth-backlog.json \
  --supersedes-receipt-id <same-department-receipt-id> \
  --replacement-reason rolling_ledger_version_preserved \
  --idempotency-key fc-YYYYMMDD-example-evidence-archive-v1
```

封存文件必须位于本项目 `backups/`，其 SHA-256 和大小须与所指回执中该活动路径的原始记录完全相同；每个变动版本由原回执部门独立登记。封存文件丢失或变化时仍会阻断，不能用此机制绕过缺失证据、跨部门归属或审批。

固定部门窗口在派工前完成替换后，先把尚无回执的工作流刷新到注册表中的新固定任务 ID：

```bash
python3 tools/flashcast_ops.py workflow-refresh-bindings --task-id fc-YYYYMMDD-example
```

该命令只允许在 `dispatch_ready` 且回执日志为空时运行；它验证新窗口的项目、cwd、健康和侧边栏绑定，并把刷新事件追加到事件链，使快照丢失后仍能恢复新绑定。

若工作流已有部门回执、尚待 QA 或处于 QA 返工，不能使用上述派工前刷新。老板批准替补、应用现场已核实新 QA 非空回复、注册表已更新并写入 `department-health-record` 后，用精确健康事件把原工作流的 QA 绑定追加替换；旧回执和结论不改写：

```bash
python3 tools/flashcast_ops.py workflow-rebind-qa \
  --task-id fc-YYYYMMDD-example \
  --old-chat-task-id <previous-fixed-qa-task-id> \
  --health-event-hash <verified-new-qa-health-event-hash>
```

此命令只接受 `evidence_received` 或 `qa_blocked`、未损坏的事件/回执链、注册表声明的旧→新 QA 替换和同项目的新窗口健康记录。之后仍须对新窗口做精确路由预检，并取得该窗口本次业务派工后的非空聊天、独立 outbox 与 QA 结论；健康回复和旧窗口的 PASS 均不能冒充新 QA 回执。

同一返工中若替换的是内容/SEO 固定窗口，使用 `workflow-rebind-department --department content-organic-website`，其余参数与上例相同。该命令只接受 `evidence_received` / `qa_blocked`、旧窗口派工回执、注册表的精确替补关系和新窗口健康事件；它追加绑定事件而不改旧回执，也不把替补健康回复当成新的内容交付。随后仍需新窗口本次业务回复、outbox、学习状态及固定 QA 复验。

固定窗口的现场健康证明有效期为 26 小时。先检查，再对过期的注册窗口发送精确健康探针；不允许用该例外派发业务：

```bash
python3 tools/flashcast_ops.py department-status

python3 tools/flashcast_ops.py department-health-record \
  --department qa \
  --task-id <registry-fixed-qa-task-id> \
  --project-id <LOCAL_PROJECT_ID> \
  --cwd "<PROJECT_ROOT>" \
  --title "FLASH CAST｜质检与Reality Checker部｜2026-09" \
  --sidebar-section-id <LOCAL_SIDEBAR_SECTION_ID> \
  --reply-ref <visible-message-id> \
  --reply-sha256 <visible-reply-sha256> \
  --reply-nonempty \
  --live-status idle \
  --last-run-status success
```

连续空回复、失败或过期会使 `dispatch_eligible=false`。不会因额度失败或单次故障自动创建替补部门；经老板批准建立替补并完成应用现场验证后，先更新注册表，再对尚未派工的工作流运行 `workflow-refresh-bindings`。

全局自动任务路由审计只读取 `~/.codex/automations`，基线只保存任务身份和提示词哈希。既有错配只标记 `quarantined_pending_owner_approval`，不自动暂停：

```bash
python3 tools/flashcast_ops.py global-routing-audit \
  --live-snapshot data/global-governance/live-thread-snapshot.json \
  --shadow
```

移除 `--shadow` 才会写入 `data/global-governance/latest-audit.json` 和 `logs/global-governance/automation-routing-ledger.jsonl`；仍不会修改任何自动任务。

存储位置：`logs/workflow-events.jsonl`、`data/workflows/<task_id>.json`、`logs/receipts/<task_id>.jsonl`、`logs/approvals/ledger.jsonl` 和 `logs/policy-decisions.jsonl`。恢复步骤见 `playbooks/controller-workflow-recovery.md`。

## Codex 子智能体委派层

固定部门在自己聊天确认接单后，可将独立、有界的内部工作交给 Codex 短生命周期子智能体。委派前先做收益和身份预检：

```bash
python3 tools/flashcast_ops.py delegation-check \
  --task-id fc-YYYYMMDD-example \
  --department content-organic-website \
  --benefit parallel_latency \
  --work-class read_only \
  --scope "独立检查三个已存在页面的 Title 重复，只读" \
  --parent-thread-id <registry-fixed-task-id> \
  --parent-project-id <LOCAL_PROJECT_ID> \
  --parent-cwd "<PROJECT_ROOT>" \
  --requested-parallelism 1 \
  --timeout-seconds 900
```

得到 `allow` 后用同一 scope 和 `decision_id` 记录启动：

```bash
python3 tools/flashcast_ops.py delegation-record \
  --task-id fc-YYYYMMDD-example \
  --delegation-id title-audit-1 \
  --department content-organic-website \
  --status started \
  --decision-id <delegation-decision-id> \
  --scope "独立检查三个已存在页面的 Title 重复，只读" \
  --idempotency-key fc-YYYYMMDD-example-title-audit-1-start
```

完成、失败、取消或超时都必须写停止原因；`completed` 还必须引用可校验的输出文件：

```bash
python3 tools/flashcast_ops.py delegation-record \
  --task-id fc-YYYYMMDD-example \
  --delegation-id title-audit-1 \
  --department content-organic-website \
  --status completed \
  --stop-reason completed \
  --evidence reports/title-audit-1.md \
  --idempotency-key fc-YYYYMMDD-example-title-audit-1-complete

python3 tools/flashcast_ops.py delegation-status --task-id fc-YYYYMMDD-example
```

限制：全项目同时最多 3 个、同部门最多 2 个，默认超时 900 秒，最多 2 次尝试。相互依赖、重叠写入、外部动作、跨项目、固定部门不健康时必须拒绝并发。委派账本只保存 scope 哈希，不保存聊天正文；子智能体完成不代替固定部门回复、outbox、QA 或老板批准。

## 初始化

```bash
python3 tools/flashcast_ops.py init
```

## Content Studio

先生成内容队列：

```bash
python3 tools/flashcast_ops.py content-queue --limit 10
```

再生成一个页面的中英文草稿包：

```bash
python3 tools/flashcast_ops.py content-draft --slot 1
```

最后做内容边界 QA：

```bash
python3 tools/flashcast_ops.py content-qa --draft-path drafts/content-studio/YYYY-MM-DD-page.md
```

Content Studio 只生成结构化草稿、媒体计划和审核记录，不登录 CMS、不上传图片、不发布网站。

## SEO 技术审计和索引对账

默认读取本地网站 URL 清单；如果当前项目还没有新清单，会只读使用 `history/` 中的历史 URL inventory，并在报告中标记为历史数据：

```bash
python3 tools/flashcast_ops.py seo-index-audit --site https://flashcast.com.my --max-urls 80
```

需要读取公开 sitemap 和页面 HTML 时，显式使用：

```bash
python3 tools/flashcast_ops.py seo-index-audit --site https://flashcast.com.my --remote --max-urls 80
```

`--remote` 只读取公开 sitemap/网页，不提交 sitemap、不请求收录、不修改网站。

## 学习记忆和周复盘

部门现在采用“三层结构”：部门主 Skill 确定职责和边界，`approved_subskills` 中的固定专业子 Skill 提供行业工作流，共享学习方法与 6 份部门记忆保存本公司的可审计经验。对应关系以 `data/department-registry.json` 和 `data/learning/department-learning-registry.json` 为准。旧 9 部门 Skill 和记忆只保留为迁移来源。

专业 Skill 包括：

- `departments/operations/SKILL.md`
- `departments/paid-growth-data/SKILL.md`
- `departments/content-organic-website/SKILL.md`
- `departments/visual-design-video/SKILL.md`
- `departments/sales/SKILL.md`
- `departments/qa/SKILL.md`

共享学习方法仍在 `skills/flashcast-department-learning/SKILL.md`。

查看注册表中每个部门是否都有自己的记忆档案：

```bash
python3 tools/flashcast_ops.py department-learning-status
```

给指定部门追加一条学习事件：

```bash
python3 tools/flashcast_ops.py department-learning-record \
  --department paid-growth-data \
  --task-id conversion-audit-001 \
  --memory-type conversion_mapping \
  --lesson "按钮点击不能直接当成有效线索" \
  --signal "GA4 有行为动作但销售真值缺失" \
  --evidence "data/analytics/ga4-consultation-actions.csv;data/leads/conversion-reconciliation.json" \
  --outcome "维持对账阻断，先补实时映射和销售回传" \
  --next-action "下次先核对 GA4 Key event、Ads 导入和 CRM 结果" \
  --confidence high \
  --lesson-status verified \
  --data-window "2026-08-01..2026-08-31" \
  --last-verified-at "2026-08-31" \
  --review-after "2026-09-07"
```

学习记录会追加到 `logs/learning-events.jsonl`，并更新对应的 `data/learning/departments/<department>.json`。它不会修改模型参数，但会让同一部门下次任务自动读取这些经验。

追加一条经过证据支持的经验：

```bash
python3 tools/flashcast_ops.py learning-record \
  --memory-type paid_search_review \
  --entity google-ads-search \
  --signal "有点击但没有主要转化" \
  --evidence "data/google-ads/2026-08-01_2026-08-30_campaigns.csv" \
  --outcome "暂不扩量，先复核转化追踪和真实线索" \
  --next-action "补齐表单、电话、WhatsApp 和销售状态对账" \
  --confidence high
```

生成周复盘：

```bash
python3 tools/flashcast_ops.py weekly-review
```

## 备份、变更日志和回滚

备份必须指定准确的文件或目录和唯一 `change-id`：

```bash
python3 tools/flashcast_ops.py backup \
  --path reports/2026-08-31-google-ads-audit.md \
  --change-id ads-landing-page-review-001
```

先做回滚预演：

```bash
python3 tools/flashcast_ops.py rollback --change-id ads-landing-page-review-001
```

真实恢复会覆盖当前文件，必须明确带上：

```bash
python3 tools/flashcast_ops.py rollback \
  --change-id ads-landing-page-review-001 \
  --apply \
  --owner-approved
```

任何包含密码、Token、Cookie、OAuth、私钥、`.env`、`.pem` 或 `.key` 的路径都会被拒绝或跳过。

## 工作区清理和历史证据保护

默认只是预览，不会移动或删除：

```bash
python3 tools/flashcast_ops.py workspace-maintenance --older-than-days 30
```

人工批准后，只会把 `drafts/` 和 `reports/` 中符合条件的普通旧产物移动到 `archive/`，不会删除：

```bash
python3 tools/flashcast_ops.py workspace-maintenance \
  --older-than-days 30 \
  --apply \
  --owner-approved
```

`history/`、`backups/`、`accounts/`、`data/` 和 `logs/` 属于保护范围。工具不会直接删除文件。

## 总控调用顺序

QA 自动日检业务入口先运行 `python3 tools/qa_dispatch_priority.py`。总控维护 `data/qa-dispatch-priority.json` 的准确任务包/源 outbox/收取决策哈希；命令只读原生回执，区分待正式派入、已派待本版结果和允许普通巡检。队列损坏或跨项目证据保持阻断；不会发送消息、写业务主账、授予发布权限或提供应用调度器硬锁。

原 QA 结果的 outbox 已由原部门登记 `evidence_replacement` 时，优先入口在完整原生回执链通过后沿该显式替换链读取当前证据，保留原 QA verdict；不会重写旧回执或将 BLOCKED 改为 PASS。无替换回执、其他部门替换、无关目标、只有 archive 或替换后再被改动的文件仍拒绝。针对检查：`python3 -m unittest discover -s tools -p test_qa_dispatch_priority.py`。

综合任务建议由 `FLASH CAST Growth Controller` 按以下顺序调用：

```text
目标 → dispatch-plan → 链式回执 → QA → 精确批准 → policy-check → 执行回执 → postcheck → workflow-reconcile
```


```bash
python3 tools/flashcast_ops.py result-handoff-record --input logs/handoffs/<项目内结果交接输入>.json
python3 tools/flashcast_ops.py result-handoff-status --task-id <原task_id>
python3 tools/flashcast_ops.py result-handoff-pending
```

输入 JSON 字段见 `data/task-contract.json#result_handoff_contract`；基础字段为 `task_id`、`event`、`sender_department`、`candidate_version`、`result_sha256`（outbox 的 SHA-256）、`outbox_path`、`idempotency_key`，可附 `evidence_paths`。新结果使用 `notification_queued`；`controller_received` 需 `intake_mode=queue`、固定来源聊天 ID、已核实非空回复的 SHA-256 与观察时间；`controller_decision` 需 `decision`、`next_owner`、`next_action` 和证据，外部阻断另需 `unblock_condition`。旧 `notification_sent` 只保留历史，当前结果的 `thread_message` 策略预检会拒绝直发总控。此项目内账本不能替代 Codex 应用现场身份核对。

部门1固定的 `fc-YYYYMMDD-website-growth-daily` 自动化轮次若没有人工派工工作流，可在核实当天 `flash-cast-4` 已完成固定聊天非空回复后，以 `source_mode=scheduled_run` 入队，另填 `source_automation_id`、`source_turn_id`、`source_thread_id`、`source_reply_sha256`、`reply_observed_at`；outbox 的 `reported_at_myt` 须是同一 MYT 日且不晚于回复。该特例只登记真实自动化来源，不生成虚构的 `dispatch_sent`、`chat_ack` 或工作流快照；其他部门与任务继续使用原派工链。

`controller_followthrough` 仍使用同一结果身份，且每次须用独立幂等键和项目内 `evidence_paths`。`followthrough_status=dispatch_sent` 需 `linked_task_id`、决策后真实 `dispatch_sent` 的 `action_receipt_id`，并核对下一负责人；`execution_verified` 需实际执行及 PASS `postcheck` 回执；`prior_action_verified` 可把决策前已实际收到的准确 outbox 关联回来，其中 `send_qa` 只接受**同原任务、同候选版本、固定 QA** 的既有 `outbox_received`，不会补造新派工；`external_wait_registered`/`blocked_with_owner` 需 `unblock_condition`、ISO 时间 `next_check_at`；`internal_control_completed` 需准确 `action_reference`。未解除的阻断或等待可凭**新的项目内证据**追加复查或真实动作，再次等待须把检查时间后移；已落实动作不可重复登记。未到检查时间的结果显示 `waiting_followthrough_review`，到期后重新出现在 `followthrough_results`。这只是控制层待办，不自动发消息或冒充业务效果。

若总控补录决策时，准确后续任务已经由同一下一负责人在**决策前**真实交付，可用 `followthrough_status=prior_action_verified`，提供不同的 `linked_task_id`、该任务 `outbox_received` 的 `action_receipt_id`、匹配原字节的 `linked_outbox_path` 和说明关联关系的项目内证据。系统记录 `action_before_decision=true`，明确这是对账，不冒充决策后的新派工，也不证明 QA、发布或业务目标完成；不相关的后续任务不得借此结项。

如果涉及线上网站、CMS、广告账户或客户外联，工具只生成方案和审批包，不代表已经执行。

## 总控结束前进度检查

`python3 tools/controller_progress.py --live-proof <项目内真实现场快照> --json-output data/controller-current-progress.json --report-output reports/company-current-work-status.md` 汇总全部注册角色、原业务主账及准确结果/决策后待办。现场快照须含真实 observed_at/threads/sections；缺 projectId 不补造，超过5分钟重读现场（不建立五分钟排程）。退出码0仅表示本次无待接续控制项；2表示仍需接续/事件等待；3表示证据读取阻断。它不发送消息、不改业务主账、不授予权限，不是应用硬锁或结束后自动唤醒功能。配套规则见 `playbooks/controller-result-continuation-and-checkout.md`。


rework3输入修复：result-handoff-record提交事件输入对象，证据用evidence_paths数组；未知/只读键、错误事件字段和类型在效果预留前拒绝。恢复已有不确定效果仍先核准确原生读回，不重发。

qa_dispatch_priority.py默认输出有界明细及总计；全量审计显式使用python3 tools/qa_dispatch_priority.py --full-audit。两种模式使用相同完整证据和优先级，不删除历史。终态原任务的准确R0返工使用initialize_workflow(..., rework_packet=冻结pin)的本项目关联载体，详见运行采用手册；原终态、原聊天及权限不改变。

## 原任务有界连续性入口

每次启动从注册表核角色和数量，核当前专业 Skill、fixed identity、scope、输入 pins、到期时间与人类控制。独立 QA/HQ采用前只做预核。准确采用后专业 R0 workpack 由 department_continuity.consume 接执行者与真实固定聊天回复观察者，执行、冻结、唯一入队和下一步都保持原任务；无下一步/到期结束本轮。不在 shell 执行未知应用 JS，不造总部派工，不把队列当自动唤醒。三助理按准确 grant 和单租约处理常规决策；重大方向/授权/R3交总部。
