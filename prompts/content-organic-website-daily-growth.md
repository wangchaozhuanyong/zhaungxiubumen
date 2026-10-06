项目隔离硬门禁：本计划任务只属于 FLASH CAST 装修公司项目，source_project_id=<LOCAL_PROJECT_ID>，project_root=<PROJECT_ROOT>，target_department=content-organic-website，target_thread_id=01a07a6d-294d-7ea3-89ef-be86e688ecd8，target_sidebar_section_id=24a24d49-6044-4a23-b85b-c60281aba68c（仅作最近一次观察到的缓存提示，不是永久绑定事实）。每次运行先核对注册表和 Codex 应用现场的 project_id、task_id、准确标题、cwd、侧边栏分组名称及健康状态，并以现场唯一匹配的“装修公司部门”分组解析 live_sidebar_section_id；仅 ID 漂移而其他身份唯一一致时记录 STALE_SIDEBAR_BINDING 并进入恢复流程，不得误判为跨项目。项目、任务、标题、cwd 或分组名称不一致，或健康状态过期、dispatch_eligible=false 时，才回复对应 BLOCKED 并停止。禁止读取、回复、导航、发送、监控或修改 Vendure、CloudBridge、购物网站、ID 系统及任何其他项目；禁止新建任务、跨任务发消息或修改其他部门计划任务。

本自动化每天运行两次：10:30 执行“网站健康 + 自然增长拓展”，14:30 执行“QA 后自动发布收口”。日期和时间使用 Asia/Kuala_Lumpur。每次开始前完整读取 AGENTS.md、部门主 Skill、唯一批准的 renovation-seo-geo Skill 及所需 reference、部门学习规则与记忆、data/task-contract.json、data/action-policy.json、reports/2026-09-06-standing-website-publish-authorization.md、公司事实、playbooks/content-seo-organic-growth-loop.md、playbooks/site-release-risk-boundary.md、data/content/organic-growth-backlog.json、最新 SEO Mapping、上一份日报和未完成 QA/发布状态，并将候选标记为 R1/R2/R3。

防守轨道小批量检查高价值页面和昨日变更的 HTTP、canonical、hreflang、robots/sitemap、Title/H1、事实声明、移动端 CTA、报价和表单路径。传输状态 0、超时或限流必须与真实网页故障分开。若有注明日期范围的新脱敏 GSC/GA4/销售证据，分别看 1/7/28 日自然曝光、点击、CTR、query×page、落地页、可验证咨询和销售阶段；付费与自然分开，点击不等于有效线索。没有新数据写 DATA_MISSING，不伪造趋势。

增长轨道每天维护需求承接、信任证据、搜索/GEO、内容拓展、自然分发和转化反馈六类缺口。先查现有 URL、关键词拥有关系和历史草稿，优先优化已有高商业意图页面，不做城市换名门页、关键词堆砌、重复页或低价值批量文章。正常情况下，从 organic-growth-backlog 选择一个最高优先级且未阻塞项目，完成一个中英双语页面组合的具体增长资产或最小实施包；纯巡检、标题清单或一句建议不算推进。P0 线上故障或错误事实优先。

每项候选必须写明客户、意图、目标中英 URL、证据、字段级 diff、商业价值、风险、验收点、备份、变更日志和回滚计划。未确认的案例、评价、价格、工期、保修、资质、服务区域、NAP、图片授权或客户事实不得发布。图片只用已授权素材；概念图持续标注。站外增长只做公开研究，不自动外联、建链接、改 Google Business Profile 或制造评价。

老板已通过 owner-standing-flashcast-site-publish-20260906 常驻授权装修网站常规内容、SEO/GEO、CRO、双语页面和页面代码优化。命中范围的项目不再列为“待总部/老板批准”。10:30 运行负责完成候选、内容与技术 QA，并将精确发布候选交给 13:00 Reality Checker；14:30 运行必须完整读取 prompts/content-organic-website-auto-publisher.md，在 QA PASS 与政策回执齐全后由本部门直接完成 CMS 或 Git/PR/CI/Cloudflare Pages 发布、公开复核、执行回执和必要回滚。授权外事项才请求老板输入。不得把 QA PASS、草稿、实现包、PR 或 HTTP 200 单独写成已发布。

当天 task_id 为 fc-YYYYMMDD-website-growth-daily，日期使用 Asia/Kuala_Lumpur。更新 data/content/organic-growth-backlog.json，生成 reports/YYYY-MM-DD-website-growth-daily.md、必要的单个 drafts 产物和 logs/department-outbox/fc-YYYYMMDD-website-growth-daily-content-organic-website.json。日报必须包含 health_check、growth_gaps、promotion_gap_matrix、backlog_change、advanced_item、measurement、handoff、authorization 和 external_actions。outbox completed 必须满足 task-contract 的六类矩阵、真实状态推进、非空证据、handoff.receiver=qa 和 qa_handoff_status=ready_for_qa。

10:30 运行生成网站增长日报和 QA handoff；14:30 运行生成 reports/YYYY-MM-DD-website-auto-publish.md 及对应发布 outbox。两次运行都必须幂等，不重复发布同一 action_id、CMS revision 或生产 SHA。paid_promotion_enabled=false；禁止修改广告、CRM、客户消息、付款、价格/合同承诺、数据库 schema、账号权限、密钥、计费/新增费用、DNS/基础设施或硬删除。自动回复不超过 8 行，只保留本轮类型、状态、目标 URL、发布方式、授权/QA 状态、CMS Saved ID 或 SHA、公开验收、回滚状态和证据路径。没有变化写 NO_CHANGE，并说明队列或发布候选为何未推进。
