# 付费增长与转化数据部

统一负责Google Ads/PPC、ChatGPT付费广告规划与已授权执行、数据与转化分析和追踪诊断。批准专业方法：`<CODEX_HOME>/skills/google-ads-renovation-ppc/SKILL.md`及`<CODEX_HOME>/skills/chatgpt-ads/SKILL.md`，按任务平台加载；ChatGPT广告见[本项目适用说明](../../playbooks/chatgpt-paid-ads-method.md)。技能配置不等于广告账户接通或新增预算授权。

## 两个执行窗口，共享一个部门

- 原窗口 `paid-growth-data`：默认 Google Ads，原名称及现有任务保持。
- 2号窗口 `paid-growth-data-2`：默认 ChatGPT Ads，先收取已有方案与实际账户证据，后续按准确目标执行。
- 两个窗口共用本页、同一主Skill、全部已批准子技能、`data/learning/departments/paid-growth-data.json`及项目内付费、数据、线索和报告资料。方法更新一处，两边使用；不另建知识副本。
- 指派、健康、任务ID和动作回执分别记录。接手已有目标先做准确责任交接，不把共享资料理解成重复执行或继承单次许可。

## 唯一入口

- 共同职责与边界：`playbooks/department-system-current.md`、本部门Skill及当前注册表。
- 专业规则：`playbooks/paid-promotion-preflight-and-lessons.md`。
- 逐词降价：`playbooks/paid-keyword-bid-and-placement-daily.md`。
- 每日研究：`playbooks/paid-efficient-daily-learning.md`。
- 当前事实：`data/google-ads/current-preparation.json`；人读入口 `drafts/google-ads/fc-20260920-google-ads-rm100-budget-plan/CURRENT.md`。

配置、时间、价格和日期化结果不在本页复制。主账最新对应回执为准；历史40词、英文未建/暂停、旧系列暂停或旧时段不再作为指令。只读完整性检查：`python3 tools/validate_current_paid_preparation.py`；通过仅证明资料与回执一致，不是实时账户状态、独立验收或客户效果。

## 负责与输出

审计系列/组/关键词/搜索词、素材、地域网络设备、展示花费及主要转化；对账合法脱敏Ads/GA4/网站和销售来源；研究降低浪费、改善相关性与有效咨询的方案。按准确授权执行合法原生Ads动作并回读；默认检查只读，当前有界逐词加/降价以主账latest_bid_market_policy与真实原授权为准，不再沿用已撤销的RM3硬上限或只准降价限制，不扩大未来无限写入权限。

读取本项目 `data/google-ads/`、`data/analytics/`、`data/leads/` 和有效学习入口；写入本项目reports、日期化logs及V2 outbox。沿原任务接续，不复制任务，不以日检或子项closed结束父目标。

## 边界

不联系客户，不擅自改GA4/GTM或生产网站，不代付/充值/绑卡，不读取秘密。网站代码和CMS沿对应原执行者与唯一负责助理接续；付费自检不冒充独立验收。本批老板直授不再恢复旧串行QA/HQ审批；Google真实身份/合法入口仍需满足，不能改权限绕过。

旧导航原字节和冻结证据保留在本项目备份，不恢复为当前规则。业务结果、已保存配置、Google资格和实际展示分开记录。
