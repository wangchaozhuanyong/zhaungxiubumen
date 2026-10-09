现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# 内容、SEO 与网站增长部持续增长 Playbook

## 目标

例行工作既守住网站健康，也持续把高商业价值的自然增长机会变成可审查、可实施、可复盘的交付物。页面数量、抓取次数、单一排名或按钮点击都不是最终成果；核心结果是有效咨询路径和能够被验证的商业页面覆盖。

## 每日双轨循环

1. **先对账**：读取上一份日报、最新 QA/授权/发布状态、`data/content/organic-growth-backlog.json`、页面关键词 Mapping、最新公开页面和注明日期范围的数据。已完成、待 QA、常驻授权可执行、授权外待老板输入和已发布必须分开。
2. **小批量健康与流量分析**：只抽查高价值页面及昨日变更，确认 HTTP、canonical、hreflang、robots/sitemap、Title/H1、CTA/表单和事实声明；同时检查最新脱敏 GSC/GA4/销售数据的数据窗口和新鲜度。数据有效时分别输出 1/7/28 日自然曝光、点击、CTR、平均排名、top queries、top pages、自然用户/会话/落地页、咨询动作和变化；付费与自然分开，点击不等于有效线索。传输失败与页面故障分开；没有新数据写 `DATA_MISSING`、最后可用日期和补数负责人。
3. **发现增长缺口**：至少评估商业服务覆盖、Location 差异、Project 证据、Blog/Materials 主题集群、内链、GEO 答案、内容新鲜度、Local SEO/公开引用和咨询阻力。先查现有 URL，不能机械新增页面。
4. **更新推广缺口矩阵**：把缺口归入需求承接、信任证据、搜索/GEO、内容拓展、自然分发或转化反馈，写清目标客户、意图、目标页面、证据、商业价值、负责人、下一产物和验收指标。
5. **排序**：优先级综合商业意图、现有证据、覆盖缺口、转化影响、工作量、依赖和风险。P0 故障/错误事实优先于拓展；没有数据时可做证据充分的结构性工作，但不得伪造趋势。
6. **连续推进并收口**：按`playbooks/organic-intensive-execution.md`连续处理最高优先级且依赖齐全的事项，形成准确候选、QA、实施和公开复核。完成一个继续下一项，不设每日数量/工时上限；纯检查、标题清单或改排期不算解决。实际权限、事实或运行环境阻断时记录检查点与唯一下一动作，下一合法窗口接续。
7. **QA、运营判断与授权匹配**：更新机会队列，在部门聊天非空回复，写日报和 outbox，随后交 QA。按 `playbooks/site-release-risk-boundary.md` 判定风险；R1/R2 在 QA 无 P0/范围内 P1后由运营记录 `AUTO_RELEASE`，再以 `flashcast.com.my:<exact-target>` 运行政策检查并由常驻授权生成当次单次精确许可；R3 才请老板决定。P2 和与候选无关的数据缺失不得无限期卡住普通优化。
8. **实施发布**：最新候选取得 QA PASS、运营 `AUTO_RELEASE` 和政策层精确放行后，当天 14:30 必须直接执行，不再等待老板逐项确认。CMS 内容只走受保护 `content-publish`；代码优化只走独立装修网站仓库的 feature branch → 检查 → PR → required CI → `main` → Cloudflare Pages 同 SHA 发布。禁止脏工作区、功能分支直发、直接写生产内容表或绕过 release guard。
9. **公开复核与回滚**：发布后核对中英文页面、Title/Meta、canonical/hreflang、Schema、sitemap、图片/alt、链接、CTA、移动端、表单路径、缓存和版本证据；严重异常按预先记录的回滚方案恢复并复检。商家资料更新、外联或客户联系仍需单独批准。

## 每周覆盖轮换

- 周一：关键词/页面拥有关系、Cannibalization、搜索意图缺口。
- 周二：住宅与商业高意图 Service 页面、CTA/CRO。
- 周三：Project 证据页、案例补证和 Materials 支撑。
- 周四：核心 Location、本地实体一致性和公开引用机会。
- 周五：Blog Topic Cluster、旧内容更新、内链和 GEO 答案块。
- 周六：报价路径、移动端、FAQ、表单及转化障碍。
- 周日：轻量健康检查、队列去重、阻塞清理和下周排序，不为凑数生产内容。

轮换是覆盖底线，不妨碍 P0/P1 优先级。发现真实机会可跨日继续，避免每天换题导致半成品堆积。

每周输出一次未来 7 天增长组合，至少说明：优先优化的既有商业页、需要新增或更新的内容资产、需要补齐的项目/公司证据、可研究的自然引用机会、预计交给 QA 的项目、常驻授权自动发布项目，以及确属授权外需要老板批准的动作。没有进入 QA、实施、发布验证或明确阻断的内容，不得计为完成。

## 机会状态

`discovered → validated → brief_ready → drafting → ready_for_qa → qa_blocked/qa_passed → standing_authorized → implementing → published → postcheck_passed → verified/closed`

授权外流程仍可进入 `waiting_owner_approval`。`blocked_owner_facts`、`blocked_data_missing` 和 `blocked_evidence_invalid` 必须写解除条件。QA PASS、授权匹配、实施完成和公开发布必须分别留证，不能互相冒充。

## 自然推广边界

允许公开研究竞争页面差距、真实行业目录/协会/供应商/项目引用机会和 Google Business Profile 内容缺口，并生成清单。禁止购买链接、PBN、链接农场、批量目录群发、垃圾客座文、假评价、虚假地点、冒充合作或未批准外联。任何站外资料修改和联系都属于外部写入。

## 每日报告最低字段

- `health_check`：检查范围、变化、证据、异常；
- `growth_gaps`：缺口、目标客户、意图、目标页面、价值与置信度；
- `promotion_gap_matrix`：需求承接、信任证据、搜索/GEO、内容拓展、自然分发、转化反馈六类缺口及下一产物；
- `backlog_change`：新增、升降级、合并、关闭及原因；
- `advanced_item`：本次推进项目、前后状态、产物路径；
- `measurement`：数据源、提取/最后可用时间、数据窗口、新鲜度、1/7/28 日自然曝光、点击、CTR、平均排名、top queries、top pages、自然用户/会话/落地页、咨询动作、自然/付费隔离、销售有效咨询证据或 `DATA_MISSING`；
- `handoff`：QA、授权外老板输入、独立网站仓库或其他部门事项；
- `external_actions`：列出常驻授权命中的精确 scope、政策决定、发布结果；授权外动作才列待批准。
