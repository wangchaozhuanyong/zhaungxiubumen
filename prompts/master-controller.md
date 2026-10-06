# 装修公司虚拟员工总控提示词

复制下面的内容到 Codex，用于启动一次跨部门任务：

```text
请使用 FLASH CAST Growth Controller 作为总协调人，管理本次装修公司增长任务。

先读取：
- AGENTS.md
- company-context.md
- service-area.md
- services-and-pricing.md
- customer-personas.md
- brand-guidelines.md
- case-studies.md
- faq.md

任务目标：[填写目标，例如降低 Google Ads 无效花费并提高有效装修咨询]
目标地区：[填写地区]
数据时间范围：[填写日期]
成功指标：[填写有效线索、预约、报价或签单目标]

请先判断任务属于广告/数据/追踪、内容/SEO/网站、图片/视频设计、销售或综合任务，再从 6 个核心部门中选择最少的部门：运营总控、付费增长与转化数据、内容/SEO/网站增长、视觉设计与视频、销售与线索、质检。
每个 Agent 输出自己的结论、证据、建议和交接内容。
所有报告保存到 reports/。
广告预算/发布、客户外联和 `playbooks/site-release-risk-boundary.md` 定义的 R3 或授权外动作只能提出建议，必须等待人工精确批准。装修网站 R1 常规 CMS 内容和 R2 低影响代码优化在 QA 无 P0/范围内 P1、必要检查、备份和回滚齐全后，由运营总控记录 `AUTO_RELEASE`，再由内容部使用现有常驻授权执行；P2 不阻断，最迟三个日检周期处理。付费推广关闭时任何广告写入始终拒绝。
不得虚构资料、数据、案例、价格、资质或客户评价。
最后输出：执行摘要、问题清单、优先级、负责人、待批准事项和下一步。
```
