# Google Ads 日检流程

## 负责人

`PPC Campaign Strategist`

## 所属核心部门

`付费增长与转化数据部`（内部合并使用 PPC、Search Query、Tracking & Measurement、Analytics 方法）

## 输入

读取最新的 `data/google-ads/` 数据、服务地区、服务价格、客户画像和 FAQ。
开始前先运行 `python3 tools/flashcast_ops.py ads-daily`，以生成数据健康、转化对账、行动队列和 Reality Checker 结果；如果状态为 `blocked`，只输出排查方案，不进入扩量或发布建议。
如果 active 输入表为空，可先运行一次 `python3 tools/flashcast_ops.py migrate-inputs` 使用旧 Skill 的脱敏历史快照；迁移数据只能作为历史参考，不能替代最新导出。

## 任务

1. 检查昨日和最近 7 天费用、点击、转化、CPA 的异常。
2. 找出高意向搜索词和疑似无效搜索词。
3. 提出否定关键词建议。
4. 检查表单、电话、WhatsApp 或预约转化是否存在数据异常。
5. 区分点击、普通线索、有效线索、报价和签单；以 `data/leads/lead-quality-log.csv` 为销售确认入口。
6. 对照 `data/analytics/ga4-consultation-actions.csv` 检查网站咨询动作，不把按钮点击当成真实线索。
7. 输出“立即检查、建议测试、暂不处理”三类事项，并同步写入 `data/action-queue.csv`。

## 强制边界

只读和分析，不修改预算、不暂停广告、不发布文案。报告保存到 `reports/`，所有变更建议标记为“待人工批准”。
