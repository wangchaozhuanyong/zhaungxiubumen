# GEO 专用方法：ai-seo

适用于 AI 搜索发现、答案准确性、引用、品牌提及与推荐优化；是专业方法补充，不改变共同工作流或发布权限。

## 使用与分工

- 已安装 `<CODEX_HOME>/skills/ai-seo/SKILL.md`，上游 `coreyhaines31/marketingskills`，版本 `2.9.0`，技能更新日期 `2026-10-15`。
- 部门2主责 GEO 问题研究、观测和可执行规划；部门1将有效改进落实为真实页面内容；部门3提供本地实体、服务地区与地图事实。三者共用同一安装，不重复制作同一任务。
- 在原目标需要 GEO 方法时加载；从技能的 Reference Routing 只读与本次问题相关的参考。已有问法、页面归属、证据及已验成果继续复用，不因安装技能重做全站审计或词库。
- 常用参考：`prompt-portfolio.md`（查询/对话样本）、`answer-accuracy.md`（错误答案追源）、`citations-vs-recommendations.md`（引用与推荐区别）、`content-patterns.md`（事实族与页面区段）、`multilingual-and-commerce.md`（语言/市场）、`content-types.md`（本地商家与商品）、`ai-attribution.md`（效果口径）。以上路径均相对于已安装技能的 `references/`。

## 官方校正与装修业务适用性

上游保留原样以便核对和升级；以下是截至2026-10-18的明确适用说明。涉及会变化的平台行为，以当前官方文档和实际观察为准，不把任何第三方技能当成平台承诺。

1. 上游关于“没有AI专项Search Console报告”的断言已过时。Google已发布[Generative AI performance report](https://support.google.com/webmasters/answer/16984139)，记录Google搜索AI功能的展示，可按页面、国家、日期和设备查看；官方说明展示不足可能看不到报告。不把看不到报告记成零展示，也不把展示记成自然用户或IP；本项目账号是否可见仍须原授权下实际读取。日期口径按平台PT说明与马来西亚业务日期分别标注。
2. [Google官方指南](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)说明：不需要特殊AI文件、特定字数或专用Schema即可获得资格。技能的40–60词、llms.txt、OKF、格式评分是可选建议或待验证假设，不能作为发布门禁、排名信号或必做清单；其他AI平台是否消费这些文件也须有该平台的证据。
3. 复用公司已确认资料和本次原任务来源。通用SaaS定价表、案例提升百分比、Wikipedia/论坛推广示例不能直接套到装修公司；不编报价、资质、项目、照片权利、评论或第三方背书。没有公开价格依据就解释计价范围及咨询条件，不能为机器读取虚构pricing文件。
4. 将抓取得到、被引用、品牌被提及、进入推荐名单、自然访问和有效咨询分别记录。AI观测注明平台/模式/日期、语言、市场及原始答案/来源；重复观测保留样本量，不以单次回答或国外研究百分比预测本公司增长。没有实测写`NOT_MEASURED`，没有合法业务数据写`DATA_MISSING`。
5. 优化落到已有唯一页面的真实缺口和可执行增量；按本次相关性改善可读正文、直接答案、来源与实体一致性，避免逐关键词或城市换名薄页。内容、代码和后台保存沿原职责与授权实施，不安装或执行参考中的第三方工具、不购买订阅、不外联发帖来“完成技能”。需要额外工具时先确认它对当前任务确有必要及已有权限。

## 维护方式

上游[技能提交记录](https://github.com/coreyhaines31/marketingskills/commits/main/skills/ai-seo)和`VERSIONS.md`可用于核对更新。当前安装固定到提交`365b412152b9542499ca1439426f7fc3cc92bb65`，安装来源与逐文件指纹记录在本项目交接目录。

后续更新复核技能目录的实际差异及上述官方校正是否仍适用；保持已审版本直到新版本检查完成，更新后读回指纹。上游持续维护不等于本机自动更新；本次没有新增定时任务、自动覆盖或审核链。

## 传统 SEO 审计补充：seo-audit

已安装 `<CODEX_HOME>/skills/seo-audit/SKILL.md`，版本 `2.2.1`，与 ai-seo 共用上游固定提交 `365b412152b9542499ca1439426f7fc3cc92bb65`。原9个文件保持上游字节，另保留根MIT许可证；来源、完整指纹与冲突审查在本项目 `reports/local-department-system-repair-20261030-v1/SEO-AUDIT-SKILL-INSTALL-20261103-v1/`。

- 方法分工：C1用 seo-audit 核技术、抓取/索引、页面与内链缺口；SEO2结合原需求、关键词和页面归属复核并制定优先级，AI搜索理解、引用与推荐仍用 ai-seo；装修事实、双语、CRO与已确认服务范围继续用 renovation-seo-geo。Local3沿原职责供本地实体事实，本次未新增其技能清单。
- 先恢复同一原task、唯一页面/关键词矩阵、已验成果和当前在途，按准确未完差异选择参考；不因新技能重跑全站审计、重建15,732词库、重复派工或解除原35项事实依赖。每项输出保留证据/时间、影响、准确动作、唯一owner、优先级和验收；报告及安装不等于实施、发布或效果。
- company.example 以马来西亚市场为准：记录实际查询地区、语言与日期；MYT与平台报表时区分别标明，币种按真实MYR资料，服务地区只用公司确认。EN/ZH与实际授权语言分别检查，不默认美国市场、不推断新增门店或服务地区。
- 本方法不改变共同规则、原任务授权、业务权限或原执行者；上游提及的其他Skill、收费服务、目录/评论外联、安装命令、自动排程、CMS/GSC修改或生产动作均不是本次技能安装附带许可。不运行可选npx/远程脚本、不注册第三方，缺数据记DATA_MISSING，AI/咨询效果无实测记NOT_MEASURED。

### 本项目适用校正

1. seo-audit主文中“每个locale必须self-canonical”的概括不能覆盖其international-seo参考的准确区分：同语言地区重复内容可选择preferred canonical并保持hreflang一致；真实不同语言译文和分页另按实际内容审查，不承诺每个URL被独立收录。依据：[Google多地区网站指导](https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites#handling-duplicate-pages-with-multilingualmulti-regional-sites)。
2. 50–60标题字符、150–160描述字符、前三句话/三条内链、一个H1、固定等待天数均为诊断提示，不是本项目硬性发布门禁或排名保证。按实际设备显示、语言、意图、可访问性和已有数据判断；低CTR不能直接证明唯一原因是标题。依据：[Google标题指导](https://developers.google.com/search/docs/appearance/title-link)、[摘要指导](https://developers.google.com/search/docs/appearance/snippet)。
3. 上游列出的Mobile-Friendly Test已退役，不把不存在的工具作为验收依赖；实际授权内可用浏览器移动端检查及现有PageSpeed/CWV证据。依据：[Google退役说明](https://developers.google.com/search/blog/2016/05/a-new-mobile-friendly-testing-tool)。
4. 不把“不要noindex薄locale页”当成一概禁令：noindex是有效索引控制，应依原页面目的和准确授权决定，不能自行改线上robots/canonical/重定向。依据：[Google noindex指导](https://developers.google.com/search/docs/crawling-indexing/block-indexing)。
5. 抓取文本或AX没有JSON-LD不能证明渲染DOM中没有Schema；同样不能断言curl从来无法看到服务器输出的JSON-LD。页面可抓取、可渲染、Google索引、AI引用及有效咨询分别取证。上游AI写作标点/用词清单只作风格参考，不作为机器生成检测或质量结论。
