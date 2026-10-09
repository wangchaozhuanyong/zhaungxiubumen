现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# FLASH CAST 免费 SEO/GEO 每日执行规范

- 适用任务：`fc-20260913-free-seo-geo-longterm` 及其每日子任务
- 主责任人：内容、SEO 与网站增长部
- 主队列：`data/content/organic-growth-backlog.json`
- 路线图：`data/content/free-seo-geo-roadmap.json`
- 时区：Asia/Kuala_Lumpur
- 费用：不新增广告、订阅、工具、会员、买链或外联费用

## 每日优先级

按`playbooks/organic-intensive-execution.md`以下顺序持续选择可执行事项；已完成一个继续下一项，主项用于标明优先级，不是当天唯一工作配额：

1. 已发布但公开复核失败、回滚未收口的 P0/P1；
2. 已 QA PASS 且等待合法发布的最新候选；
3. QA 给出明确最小返工的候选；
4. 已有证据、无外部依赖的 P0/P1 页面或内容资产；
5. 数据补齐、页面拥有关系、技术健康、AI 固定问题基线；
6. 只有在真实事实和查询证据支持时，制作新的 Blog、Project、Location 或站外机会。

旧条目已经 `verified/closed` 时只监控，不重复制作。真阻断时切换到另一个无依赖的有效项；不得用全面重复巡检、空报告或硬凑文章代替增长产物。

## 每日时序

### 10:30及接续窗口：连续推进真实资产与修复

1. 读取公司事实、前一日结果、主 backlog、路线图和未闭环发布状态。
2. 刷新数据新鲜度：GSC、GA4、销售、公开页面、CMS/Git 版本分别记录日期与范围。
3. 从优先级规则选择当前主项，写明目标客户、意图、唯一页面、证据、依赖、风险和验收；完成后连续选择下一可执行项，以实际队列决定工作量。
4. 至少推进一个阶段，例如：`discovered → validated → brief_ready → ready_for_qa`，或完成明确返工。
5. 产物必须是可验收内容之一：字段级候选、双语 brief、页面拥有关系、内链图、GEO 答案块、项目补证清单、技术/CRO 包、数据基线或站外机会清单。
6. 更新主 backlog；路线图只保存编排与引用，不复制另一套互相冲突状态。
7. 在固定内容部聊天非空汇报后写 outbox；候选需要 QA 时生成不可变快照与 manifest。

### 13:00 QA：独立验收

- 核对事实、EN/ZH 一致性、唯一页面归属、目标记录/URL、字段 diff、链接、Schema/CTA、数据新鲜度、备份和回滚。
- 只以 P0 或本次范围内 P1 阻断；P2 记录并安排最迟三个日检周期处理。
- 锁定唯一发布通道：`cms_content_candidate → cms_write` 或 `site_code_candidate/site_code_rework_candidate → site_publish`。
- `PASS` 必须有范围、候选版本和证据；`BLOCKED` 必须给最小返工范围与复验条件。

### 14:00 运营：放行或返工

- R0 内部项直接登记结果。
- R1/R2 在 QA PASS 后记录 `AUTO_RELEASE`，用 `flashcast.com.my:<exact-scope>` 取得单次精确许可。
- 通道、action_id、scope、候选版本或证据不一致时拒绝。
- R3、授权外或无法安全回滚时才请求老板准确批准。

### 14:30 内容部：发布/返工收口

- QA PASS + `AUTO_RELEASE` + 精确 policy allow 齐全后，当天执行，不再等待逐项确认。
- CMS 字段只走受保护 `content-publish`：先即时版本检查和全批 dry-run，再逐条 publish；任一失败停止剩余写入。
- 代码只走独立网站仓库 Git/PR/CI/main/同 SHA 部署；不以 CMS 或本地构建冒充部署。
- 发布后核对 CMS Saved ID/`updated_at` 或生产 SHA、目标公开页面、EN/ZH、目标链接/Schema/CTA、缓存和回滚状态。
- QA 阻断且范围明确时，同一阻断项每日最多自动返工两次；再次失败保留真实阻断。

### 15:00 公司最终汇报

报告必须分开写：部门交付、QA、运营批准、实际执行、生产复核和效果数据。每项说明：

- 今天做了什么；
- 证据/产物路径；
- QA 结论；
- 发布通道与 policy/approval；
- CMS Saved ID 或生产 SHA；
- 线上验收和回滚状态；
- GSC/GA4/销售/AI 的日期范围与结果；
- 阻断、负责人和下一步。

计划、QA PASS、policy allow、CMS saved、HTTP 200、排名和业务结果是不同阶段，不能相互冒充。

## 每周循环

| 日别 | 重点 | 可交付示例 |
|---|---|---|
| 周一 | 数据与优先级 | GSC/GA4/销售新鲜度、query×page、未来 7 天队列 |
| 周二 | 高意图 Service | EN/ZH 页面 brief、答案块、CTA/内链字段候选 |
| 周三 | 决策型内容 | 现有 Blog 更新、Service/Materials/Quote 关系 |
| 周四 | 技术、GEO 与本地实体 | robots/canonical/hreflang/Schema、固定 AI 问题、NAP |
| 周五 | 项目/材料/自然引用 | 证据包、权利清单、合规免费机会；无事实则换项 |
| 周六 | 发布收口与轻量健康 | 未闭环发布、移动端/公开复核、回滚检查 |
| 周日 | 周复盘与下周编排 | 完成/失败/阻断、有效资产、7 日队列与学习 |

日别是默认主题，不覆盖“先收口已 QA PASS/发布异常”的更高优先级。

## 每月循环

1. 使用当前完整 28 天与前 28 天 GSC、GA4、匿名销售数据；缺失写 `DATA_MISSING` 和最后可用日期。
2. 按 branded/non-branded、Service/Blog/Location、language、country=Malaysia、device 分段。
3. 复盘 Top 10/3/1 查询覆盖、CTR、页面拥有关系、自然落地页、咨询动作和 qualified/quote/won。
4. 固定 AI 问题在可比平台、国家定位、语言和登录上下文下复测，分开统计 mention/citation/recommendation/accuracy。
5. 保留产生真实价值或改善决策体验的页面；URL 合并、redirect、canonical、noindex、删除只形成 R3 方案。
6. 重排未来 90 日；每 90 日滚动，不因 90/365 日节点自动结束。

## 状态与证据合同

- 主 backlog 只使用其 `allowed_statuses`；路线图的排期字段 `status` 只使用 `planned/ready/in_progress/blocked/done`，具体等待原因写入 `status_detail`，并必须引用 backlog id。真实执行阶段仍以主 backlog 和工作流回执为准。
- `DATA_MISSING`、`NOT_MEASURED`、`BLOCKED_OWNER_FACTS` 与数值 0 含义不同。
- 每次候选快照至少包含：source path、SHA-256、候选版本、目标记录/URL、changed fields、expected version、acceptance、rollback。
- 活动 backlog 和学习文件会变化，不作为唯一不可变证据；每轮 QA 使用 `reports/evidence/<date>-<task>/manifest.json`。

## 免费工具与外部动作边界

- 可用：公开 HTTP/DOM 检查、现有项目脚本、GSC/GA4 合法脱敏导出、Search Console/Rich Results/PageSpeed/Bing 文档、人工可比 AI 问题测试。
- 不默认执行：登录、索引提交、GBP/Apple/目录认领或修改、第三方外联、客户联系、评论请求、付费会员、收费 API、试用转付费。
- IndexNow 或 URL submission 即使免费仍是外部写入；需独立授权和回执，且不保证收录/排名。

## 停止与重试

- 立即停止当前项：生产版本冲突、QA P0/P1、通道不匹配、目标记录错误、事实/图片权利不明、凭据/OTP 缺失、外部平台拒绝、公开复核失败。
- 不循环重试：权限、OTP、事实、账号归属、收费或第三方审核阻断。
- 可安全重试：短暂网络/平台失败，最多两次且使用同一幂等键；仍失败则记录实际错误和负责人。
- 发布后公开失败按预设回滚；不通过直接数据库写入或复制浏览器令牌绕过受保护链路。
