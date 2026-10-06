# 内容、SEO/GEO 与网站门禁

先按 `playbooks/site-release-risk-boundary.md` 判定 R1/R2/R3，再只检查与本次改动相关的门禁：公司事实、服务/地区、双语一致、搜索意图和页面拥有关系、目标字段或文件 diff、相关 title/H1/canonical/hreflang/sitemap/robots/Schema、概念图标注、案例/评价证据、受影响 CTA/表单/移动端、备份/变更/回滚和生产目标。

以下情况不得放行：虚构价格/工期/案例/资质；假城市门页；概念图冒充完工；关键页面 noindex/robots/canonical 错误；表单不可用；中文和英文承诺不一致；没有明确生产目标或回滚。

技术检查通过不等于保证排名、收录、AI 引用、流量或线索。

P0 和本次范围内 P1 阻断；P2 记录负责人和三次日检内的到期日后放行。GSC/GA4/销售数据缺失只阻断效果结论。纯文字、Meta、FAQ、alt 或已有内链的 R1 修改不要求全站浏览器和全量 CI；CMS 回读、公开 HTML/链接和双语目标页足够。布局、表单、交互和 R2 代码必须验证受影响视口/流程及匹配范围的测试、typecheck、build。
