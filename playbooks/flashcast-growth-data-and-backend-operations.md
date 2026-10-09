现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# FLASH CAST 增长数据与后台只读作业手册

版本：2026-08-31  
来源：`<USER_HOME>/Desktop/skill中心/skill-zhuangxiuseogeo` 的 Google Ads PPC、SEO/GEO、追踪、增长智能和只读审查方法。  
适用范围：本项目的营销总控、Google Ads、GA4、网站后台、线索和销售数据分析。  
默认模式：`audit`（只读审计）或 `draft`（生成本地方案）。

## 1. 继承原则

本项目继承源 Skill 的方法、字段、证据门槛和安全边界，不复制整套源仓库，也不复制密码、Token、Cookie、OAuth 文件、OTP、银行卡或客户个人资料。源 Skill 的完整历史资料仍在：

`<USER_HOME>/Desktop/skill中心/skill-zhuangxiuseogeo`

当前项目已经保留一份历史资料索引在 `history/skill-zhuangxiuseogeo/`。以后的最新数据应放到当前项目的 `data/`，不能把历史快照误当成实时状态。

## 2. 总控和员工分工

每次任务由 `FLASH CAST Growth Controller` 先确认目标、地区、语言、时间范围、成功指标和审批边界，再调用最少的必要员工：

| 任务 | 负责人 | 交付重点 |
|---|---|---|
| 总体协调 | `FLASH CAST Growth Controller` | 任务拆分、证据门槛、优先级、交接 |
| Google Ads 账户审计 | `Paid Media Auditor` | 账户、系列、预算、地域、设备、结构和风险 |
| PPC 策略 | `PPC Campaign Strategist` | 服务分组、匹配方式、预算顺序和测试方案 |
| 搜索词/否定词 | `Search Query Analyst` | 搜索意图、浪费候选、否定词分层、隐藏搜索词 |
| 广告文案 | `Ad Creative Strategist` | CTR、文案主题、资产、CTA、落地页匹配 |
| 追踪 | `Tracking & Measurement Specialist` | GA4、GTM、Google Ads 转化、表单、电话、WhatsApp、离线回传 |
| 数据汇总 | `Analytics Reporter` | 指标计算、时间窗、归因和成本对账 |
| 网站转化 | `UX Architect`、网站负责人 | 移动端流程、表单、CTA、页面消息匹配；不直接改生产网站 |
| 销售真值 | `Sales Outreach`、销售负责人 | 实际入站、有效线索、预约、报价、签单、失单原因 |
| 证据审查 | `Evidence Collector`、`Reality Checker` | 区分事实、推断、缺失和过期数据 |

不要重复安装或复制大量泛用 Agent。广告/PPC 和 SEO/GEO/CRO 各有明确入口，方法由总控统一串联。

## 3. 数据真值层级

报告必须按下面的优先级解释数据：

1. 负责人确认的真实线索质量、报价、签单和收入；
2. 可核验的网站成功表单、WhatsApp Business 实际入站、真实接通电话；
3. GA4 的成功表单和咨询动作；
4. Google Ads 的主要转化和平台转化动作；
5. 点击、展示、CTR、会话和按钮点击。

下面几项不能直接当成客户数：

- WhatsApp 按钮点击不等于 WhatsApp 实际发出或收到消息；
- `tel:` 电话按钮点击不等于接通或有效咨询；
- `generate_lead`、表单开始、页面浏览是诊断信号，不是业务真值；
- 各事件行的 unique users 不能相加，去重必须在同一范围内完成；
- Google Ads 的 “All conversions” 可能包含平台观察动作，不得直接当作实际客户数。

## 4. 每次刷新必须统一记录的元数据

每份导出、报告或快照都应记录：

- 数据来源、账号/网站、客户 ID 或属性 ID（可脱敏）；
- 开始日期、结束日期、采集时间、马来西亚时区；
- 货币（目前按 RM/MYR 记录，必须和账单核对）；
- 报表名称、筛选条件、是否含 Google 汇总行；
- 数据状态：`fresh`、`stale`、`partial`、`missing`、`invalid`；
- 是否可用于决策；
- 与上一期相比的新增、变化和不可比原因。

不同账号、不同时间窗或不同货币的数据不能相加。当前本项目的 Ads CSV 是 2026-08-01 至 08-30，而源 Skill 的 GA4 对账窗是 2026-08-02 至 08-31，必须在同一时间窗和同一账户范围内重新对账。

## 5. Google Ads 只读登录与审查流程

### 5.1 登录边界

只使用负责人已经打开的 Google/Chrome 登录态或正式授权的只读连接。不得索要、读取、保存或复制密码、验证码、Passkey、Cookie、Token、API Key 或支付资料。

如果出现 OTP、Passkey、CAPTCHA、设备验证、账单验证或权限不足：停止在该页面，提示负责人本人完成验证；不能绕过，也不能让 Agent 代为确认。

### 5.2 进入账户后只读记录

先截图或记录当前账户名称、客户 ID、货币、时区、时间范围和权限，再依次查看：

1. Campaigns：名称、状态、类型、预算、花费、展示、点击、CTR、CPC、主要转化、全部转化、出价策略、网络；
2. Ad groups：广告组、服务意图、最终 URL、展示、点击、花费、转化；
3. Keywords：匹配方式、质量得分（若有）、展示份额、点击、花费、转化、状态；
4. Search terms：真实搜索词、关键词、广告组、地区、设备、点击、花费、转化；重点查看 `其他搜索字词`；
5. Ads/assets：标题、描述、资产、最终 URL、广告强度、审核状态、CTR、转化；
6. Devices：手机、电脑、平板的展示、点击、花费、转化；
7. Locations：城市、邮编、半径、实际所在地/兴趣地、展示、点击、花费、转化；
8. Conversions：转化名称、来源、类型、主要/次要、是否纳入 “Conversions”、计数方式、归因、窗口和最近记录；
9. Campaign conversion goals：哪些目标可用于出价；
10. Change history、Recommendations、auto-apply：只读取，不执行建议、不点击 Apply/Save/Enable；
11. 自动标记、最终 URL 参数和 UTM：只记录是否存在，不现场改写。

### 5.3 严禁点击

不得执行恢复、启用、暂停、删除、提高预算、改变出价、放宽匹配、扩大地域、添加/删除否定词、切换主要转化、启用 PMax/Display/Search Partners/AI Max、应用 Recommendations、修改账单或发布广告。

所有上述动作只能写进报告的“待人工批准方案”。

## 6. GA4、GTM、网站后台只读流程

网站代码位于独立网站项目，本中控目录只保存审计、字段、报告和交接，不直接改生产网站或 CMS。

### 6.1 GA4 Admin/Reports

只读核对：

- Property、Data stream、网站域名、Measurement ID、时区和数据保留；
- Google tag/GTM 是否存在，是否重复安装；
- 事件命名和参数：`phone_click`、`whatsapp_click`、`quote_form_success`、`contact_form_success`、`generate_lead`；
- 哪些事件标记为 Key event，哪些导入 Google Ads，哪些属于主要转化；
- Paid Search 的 source/medium、campaign、landing page、用户、会话、engaged sessions 和咨询事件；
- 跨域、自动标记、GCLID/GBRAID/WBRAID 是否被保留；
- DebugView、Tag Assistant 或浏览器网络请求中的触发证据。

### 6.2 表单

用手机和电脑各进行一次明确的测试（测试资料必须是测试资料），只验证：

- 必填校验、提交按钮、加载状态、错误状态；
- 成功状态或 thank-you 状态是否只出现一次；
- GA4 成功事件是否触发，失败提交是否不会被记成成功；
- Google Ads 转化是否收到；
- 邮件是否到达唯一主收件箱和备用转发；
- 来源、Campaign、GCLID 等字段是否在后台/CRM 保留；
- 去重 ID、时间、货币和值是否合理。

测试结束后要在记录中标记为测试数据，不能计入真实客户。

### 6.3 电话和 WhatsApp

- 电话拆分为按钮点击、实际接通、通话时长、有效咨询；
- WhatsApp 拆分为按钮点击、实际发出、Business 入站、有效对话、预约、报价；
- 电话和 WhatsApp 的点击事件只做辅助观察；实际业务结果需由销售/CRM 确认；
- 不在后台直接发送 WhatsApp、邮件或客户消息；
- 不把客户完整姓名、完整电话、邮箱、身份证或聊天全文写入当前项目。

### 6.4 网站后台/CMS

只读查看表单收件设置、线索列表、事件脚本、发布状态和错误日志。生产修改、CMS 发布、数据库写入、代码部署、域名/DNS/服务器变更均需独立明确批准，并不包含在 Google Ads 审计授权内。

## 7. 当前项目需要的标准数据文件

建议后续每月或每次审计补齐以下脱敏文件：

| 文件 | 最低字段 | 用途 |
|---|---|---|
| `data/google-ads/campaign-performance.csv` | date, campaign, status, spend_myr, impressions, clicks, ctr, avg_cpc, primary_conversions, all_conversions | 预算和账户趋势 |
| `data/google-ads/ad-groups.csv` | campaign, ad_group, landing_page, impressions, clicks, spend_myr, conversions | 结构判断 |
| `data/google-ads/keywords.csv` | campaign, ad_group, keyword, match_type, impressions, clicks, spend_myr, conversions, quality_score | 关键词决策 |
| `data/google-ads/search-terms.csv` | date, search_term, campaign, ad_group, keyword, device, location, clicks, spend_myr, conversions | 搜索意图和否定词 |
| `data/google-ads/ads.csv` | campaign, ad_group, ad_id, headlines, descriptions, final_url, impressions, clicks, spend_myr, conversions, ad_strength | 文案和落地页匹配 |
| `data/google-ads/devices.csv` | device, impressions, clicks, spend_myr, conversions | 设备体验 |
| `data/google-ads/locations.csv` | location, location_type, impressions, clicks, spend_myr, conversions | 地区投放 |
| `data/google-ads/conversion-actions.csv` | action, source, type, primary, included_in_conversions, count, value, date | 转化设置 |
| `data/analytics/ga4-traffic-acquisition.csv` | date, landing_page, channel_group, source_medium, campaign, users, sessions, engaged_sessions, event counts | 网站流量和归因 |
| `data/analytics/ga4-consultation-actions.csv` | window_start, window_end, scope, event_name, event_page, source_medium, campaign, action_count, unique_users, sessions | 咨询动作对账 |
| `data/leads/lead-quality-log.csv` | lead_id, date, source, campaign, service, area, status, quote_value, won, loss_reason | 真实线索质量和 ROI |
| `data/spend-reconciliation.csv` | date_start, date_end, account, channel, source_document, spend_myr, tax_or_fee_note | 账单、广告和渠道成本对账 |

线索表只用脱敏 ID；状态至少区分：新线索、已联系、有效线索、已预约、已量房、已报价、谈判中、已签单、未成交、无效线索。

## 8. 每周增长控制循环

1. `Analytics Reporter` 检查来源是否 fresh、时间窗是否一致、是否存在重复总计行；
2. `Tracking & Measurement Specialist` 对账 GA4、Google Ads 和网站/CRM；
3. `Search Query Analyst` 审核搜索词和隐藏汇总，提出精确否定词或条件性否定词；
4. `Paid Media Auditor` 检查广告系列、广告组、设备、地区和落地页；
5. `Ad Creative Strategist` 按有量样本比较 CTR 和服务主题，不能把小样本当赢家；
6. `Sales Outreach` 补齐实际沟通、有效性、报价和签单；
7. `Evidence Collector` 和 `Reality Checker` 检查结论是否越过证据；
8. 总控生成 `reports/YYYY-MM-DD-*.md`，把所有账户修改、网站发布和客户外联列为待批准。

刷新节奏建议：新投放前先做一次完整验收；上线后前 72 小时频繁观察；之后每日看异常、每周看搜索词/地区/设备/广告和线索质量、每月做成本对账。没有稳定有效转化时，不扩量、不恢复 PMax、不把自动出价学习建立在按钮点击上。

## 9. 当前工作分配建议

| 优先级 | 工作 | Agent/负责人 | 产出 |
|---|---|---|---|
| P0 | 统一 RM700–800 总开支和 11 个实际咨询的来源、日期、渠道 | `Analytics Reporter` + 公司负责人 | 成本/线索对账表 |
| P0 | 用当前登录态只读核对 Ads、GA4、GTM、网站后台 | `Tracking & Measurement Specialist` + `Paid Media Auditor` | 只读证据包 |
| P0 | 给 11 个实际咨询分配匿名 ID、来源、服务、地区、状态 | 销售负责人 + `Sales Outreach` | 脱敏线索质量表 |
| P1 | 对齐 GA4 成功事件与 Google Ads 主要转化 | `Tracking & Measurement Specialist` | 转化映射和验收清单 |
| P1 | 获取完整搜索词，拆分服务组并准备否定词草案 | `Search Query Analyst` + `PPC Campaign Strategist` | 待批准关键词方案 |
| P1 | 移动端表单、电话、WhatsApp 体验验收 | 网站负责人 + `UX Architect` | 测试记录和问题清单 |
| P2 | 建立每周增长报告和学习记忆 | 总控 + `Analytics Reporter` | 周报、行动队列、复盘 |

## 10. 审批与交接

默认允许：读取资料、读取已有导出、只读检查、计算指标、写本地报告、生成草案。  
默认不允许：广告预算/出价/关键词/状态/转化设置修改、网站生产修改、CMS 发布、发送客户消息、支付、对外承诺。

每个交接必须写明：结论、证据文件、数据时间窗、缺口、建议动作、负责人、优先级、风险、是否需要公司负责人批准、下一步和截止时间。
