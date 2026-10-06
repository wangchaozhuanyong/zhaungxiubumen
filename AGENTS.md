## 2026-10-07 部门系统现行规则

本轮按 `playbooks/department-system-current.md` 执行：11个固定角色，总部审核派工、助理预核、质检1/2独立分工；先核实际结果再决策和关联下一动作。旧部门数量和旧通知方式失效，历史证据/权限不改。部门先固定聊天非空回报，再冻结V2/唯一入队及回读；普通结果不发送到其他聊天，不打断active。依赖齐全的已冻结同任务R0步骤按准确输入/步骤指纹继续；停止必列未完成、负责人、下一动作和解除条件。机器准入尚未通过的QA2/发布权限仍不启用，不新增高频轮询。


## 2026-10-05 老板新增后台发布部门（接管准备）
老板指定总控只派工/审核，新增 publishing 后台发布部，主Skill departments/publishing/SKILL.md，方法 skills/flashcast-cms-publishing/SKILL.md。当前批次原负责人完成后按准确候选移交；新部固定绑定和独立QA/真实CMS执行者准入未完前只有R0准备，不继承旧许可或消费记录。后台内容发布归新部；代码修改/PR/CI/部署归老板明确指定的装修网站开发项目已有聊天“同步管理后台与客户端功能”<WEBSITE_DEVELOPER_THREAD>，准确项目<WEBSITE_PROJECT_ID>。该单独人类授权不开放其他跨项目路由或生产权限。状态以data/publishing/department-onboarding.json为准，原专业部门制作候选、固定QA独立验收、总控收取决策；不新增高频轮询。

# 装修公司虚拟员工中控项目

## 2026-09-30 固定部门每日专业工作与总控闭环

老板明确要求七个固定执行部门每天按各自专业目标主动检查、研究、实施或提交准确候选，并检查以往有没有漏做的必要方法和未达标原因；每日任务不是每天只做一项，也不是单纯写巡检报告。统一执行 `playbooks/department-daily-professional-loop.md`。销售、付费数据和视觉部门也做本部门每天的安全只读/内部工作；Google Ads 继续 HOLD/OFF/RM0，销售不自行联系客户，视觉不擅自发布或新增费用。

部门每轮无论完成、部分完成、失败或外部阻断，先在本部门固定聊天报告实绩、未完范围、证据、专业新增机会、唯一下一负责人和解除条件，再校验 V2 outbox。需要总控决策的结果进入项目持久队列 `notification_queued`，不向总控聊天直接插话；总控在自然接续和每日18:00兜底核对后登记 `controller_received`、`controller_decision`，并沿原任务继续派 QA、返工、合法实施或下一有界工作。决策不算动作完成；未取得真实派工/执行回执或具名外部等待与复查时间时，仍列 `followthrough_results` 待办。部门 active 时普通任务排队，不打断。每天15:00汇总八角色的真实进度；单轮 closed 或日报完成不代表业务目标完成。自然搜索50个去重IP/日无合法口径和新鲜数据时保持 DATA_MISSING。

## 2026-09-27 GEO主责与执行要求

老板指定seo geo推广部门2（seo-content-research）为GEO专业规划、研究、内容候选及持续优化主责。GEO指AI搜索/答案中的理解、引用、品牌提及与推荐，不能用地区词或地图工作代替。部门2先依据专业Skill、最新主要来源和真实站点全面盘点，交完整任务方案，集中推进所有依赖齐全的初期问题，后续每日主动检查、分析、修复、拓展。专业范围与次序由部门2判断；总控负责依赖、派工与收口。网站实施仍归部门1，本地实体/地图事实由部门3配合，固定QA独立验收。唯一任务主账、原任务引用和生产权限不变；无实际AI观察或来源数据时标NOT_MEASURED/DATA_MISSING。执行入口为logs/handoffs/2026-09-27-geo-department2-foundation-v1.md，日常接续合并进部门2已有自动化，不另建重复任务。

## 2026-09-27 最新持续优化要求

## 2026-09-28 固定部门结果通知与自然搜索目标

2026-09-30老板纠正：结果通知不得打断总控或任何正在工作的固定部门。下文曾允许“总控 active 仍可发送”的例外已撤销；新的部门结果一律先在原部门聊天非空回复、保存并校验 V2 outbox，再以原 task_id／候选版本／结果哈希运行 `result-handoff-record` 登记 `notification_queued` 到项目内持久队列。不得调用 `send_message_to_thread` 给总控推送普通结果，即使总控现场显示 idle 也不使用发送前状态检查来赌无竞态。总控每次自然接续和每日18:00兜底先运行 `result-handoff-pending`，核对原聊天、outbox、QA/执行层级后写 `controller_received`（`intake_mode=queue`）和 `controller_decision`；然后从最新 `controller_checkpoint` 继续原本未完任务。入队不等于已送达聊天、已决策、已发布或业务目标完成。旧 `notification_sent` 保留历史事实，不补造或重发。此段优先于下文旧“active 可通知”语句。


自然搜索目标为最终达到同一马来西亚完整日内网站自然来源至少50个去重IP访问；合法IP来源、去重口径与GA4/GSC对账未确认前，目标进度记 `DATA_MISSING`，不能用自然活跃用户、会话或GSC点击冒充IP。SEO/GEO部门持续查漏、提出可证实候选，网站部实施，固定QA独立验收；发布、公开复核、排名/流量和有效咨询分层记录，未达到目标或未完成依赖齐全的专业工作就继续优化，不以词库或文件数量结项。

老板要求前期集中完成全站基础及可执行积压，之后持续主动检查、分析、解决问题与扩展。执行`playbooks/organic-intensive-execution.md`和`data/content/organic-execution-policy.json`，覆盖所有旧每天一项、唯一主项、一个核心交付物及维护期数量/工时节流；按真实可执行队列连续推进。初期完成与维护切换须有覆盖及解决/发布/公开复核证据，外部事实/权限/数据阻断保留真实未完成。active窗口不打断，原任务和唯一主账保留。网站原精确授权、QA、备份回滚、通道及重试安全边界不变；14:30仍必收口，其他合法窗口可收口已精确放行的动作。总控需持续收取回传、恢复健康及解除控制阻断，不得只写汇报。

## 2026-09-27 老板授权新增SEO部门（当前规则）

老板明确要求新增两个部门以分担SEO。当前固定团队为8个角色：1个operations总控与7个执行部门。新增seo-content-research（seo geo推广部门2）、local-seo-maps（seo geo推广部门3），均位于“装修公司部门”，主Skill和唯一批准renovation-seo-geo路径以注册表为准。下文旧“6角色/5执行部门”数量和SEO全部合并职责由本节覆盖；原绑定、历史交付和审批证据保留。

seo-content-research负责自然需求研究、关键词、主题与双语内容草稿；local-seo-maps负责地图、本地实体、地区内容brief和真实信任资料；content-organic-website保留技术SEO、网站代码/CMS实施与生产复核。网站常驻授权执行部门仍为content-organic-website，不自动扩展为新部门生产写入权限。广告、客户联系、账号权限等边界不变。

原active任务由原负责人完成当前轮次，不因扩编中断或并行重做；后续以准确交接、原任务引用和唯一backlog接续。总控可向注册表中现场验证的7个执行部门派工，原精确路由、健康、QA、发布门禁全部适用。每日公司报告按注册表列出全部8角色；新增部门各自须有可见固定窗口、非空回复、记忆和实际产物，不用文件冒充部署。

初期集中建设优先于旧每日一项节流，按依赖和互不重叠责任推进；完成后进入每日维护与持续拓展。跨部门消息及自动任务仍由operations经过现场验证和policy-check操作。

## 项目定位

这是装修公司的营销、广告、内容、销售和数据运营中控目录，不是装修网站代码仓库。网站代码应在独立的网站项目中维护；本目录只保存业务资料、分析报告、营销计划、审批记录和 Codex Agent 配置。

## Codex 工作规则

1. 开始任何任务前，先读取与任务相关的公司资料：`company-context.md`、`service-area.md`、`services-and-pricing.md`、`customer-personas.md`、`brand-guidelines.md`、`case-studies.md`、`faq.md`。
2. 先确认任务目标、目标地区、数据时间范围和成功指标；资料缺失时明确列出缺口，不得编造公司资质、案例、价格、评价、客户数据或广告数据。
3. 只选择完成任务所需的最少 Agent。当前活动团队共有 6 个固定角色窗口：1 个运营总控和 5 个执行部门（付费增长与转化数据、内容/SEO/网站增长、视觉设计与视频、销售与线索、质检）；装修营销跨部门任务由 `FLASH CAST Growth Controller` 负责分派。总控不是执行部门，也不得向自己派专业任务。
4. 独立部门聊天必须以 `data/department-registry.json` 为准；聊天任务是 Codex 应用状态，必须在任务列表和导航中验证可见，不能用文件或后台 ID 冒充可见窗口。
5. 每个交付物必须包含：结论、依据、具体动作、负责人、优先级、风险和下一步。
6. 结论和建议保存到 `reports/`；可重复的流程保存到 `playbooks/`；可复用提示词保存到 `prompts/`。
7. 历史 SEO/GEO 资料在 `history/skill-zhuangxiuseogeo/`，默认只读；新的部门工作记录写入 `departments/`、`logs/` 和 `reports/`。
8. 账号分工只看 `accounts/ACCOUNT-INDEX.md` 和 `accounts/DEPARTMENT-ACCESS-MAP.md`；密码、Token、Cookie、OAuth 文件和私钥禁止进入项目目录。
9. Google Ads 的预算、出价、暂停广告、发布广告和对外客户承诺，都必须先输出方案并等待人工明确批准。装修网站 `flashcast.com.my` 的常规内容、SEO/GEO、CRO 和页面代码优化适用老板在 2026-09-06 授予的常驻发布授权 `owner-standing-flashcast-site-publish-20260906`：内容、SEO与网站增长部在事实、双语、QA、备份、变更日志、回滚和发布门禁全部通过后直接实施并发布，不再逐次请示运营总控或老板。
10. 不在本目录保存密码、API Key、Token、银行卡、客户身份证件或其他敏感信息。广告数据和线索数据使用脱敏导出。
11. 每次任务结束时说明：读取了哪些资料、使用了哪些 Agent、发现了什么、生成了哪些文件、哪些动作仍需人工确认。
12. 每个部门任务开始前必须读取注册表中的唯一 `professional_skill`、本部门 `approved_subskills` 白名单、`skills/flashcast-department-learning/SKILL.md` 和自己的学习记忆。付费部只可调用 `google-ads-renovation-ppc`，内容/SEO/网站部只可调用 `renovation-seo-geo`，视觉部只可调用 `full-house-custom-ad`、`imagegen`、`hyperframes`、`media-use`，销售部只可调用 `renovation-sales-ops`；运营和 QA 不调用专业子 Skill。禁止临时选择白名单外或其他部门 Skill。完成后先在本部门聊天回复，再记录有证据支持的学习事件。主/子 Skill 负责岗位方法，部门记忆负责历史经验；这不是修改模型参数。
13. 运营总控聊天收到命中非 `operations` 部门的专业任务时，必须先生成分派计划，再把任务包发送到注册表中已验证的固定部门任务并等待回传；发送前不得调用目标部门专属 Skill、不得制作目标部门交付物。发送失败或部门不可见时必须标记 `blocked`，禁止由总控代做。用户说“其他你们决定”只代表目标专业部门可自主决策，不代表总控可以绕过部门路由。
14. 发送任何 Codex 任务消息或创建/更新计划任务前，必须用 Codex 应用现场状态核对来源项目、目标项目、目标部门、固定任务 ID、任务标题、`cwd` 和注册表中的侧边栏分组 ID，再运行 `policy-check` 的 `thread_message`、`automation_create` 或 `automation_update` 路由预检。运营总控固定窗口位于“装修公司总控”，5 个执行部门固定窗口位于“装修公司部门”；不得把两类分组混用。只有 `routing_allowed` 才可继续，`dispatch_sent` 必须引用该放行记录。FLASH CAST 默认拒绝向 Vendure、CloudBridge、购物网站、ID 系统或任何注册表外项目发送消息或建立计划任务；项目或绑定信息缺失时按 `blocked_cross_project` 处理。此门禁是项目级控制，不能声称会拦截本项目流程之外的所有 Codex 工具调用。
15. 固定部门窗口可在 `data/delegation-policy.json` 允许时使用 Codex 短生命周期子智能体，但必须先通过 `delegation-check`，仅拆分独立、有界且收益明确的内部工作。项目并发上限为 3，单部门为 2，默认超时 15 分钟，最多 2 次尝试；相互依赖、写入范围重叠、外部动作、跨项目或固定窗口不健康时必须串行或阻断。子智能体是部门内部短工，不得使用 `create_thread`、`fork_thread` 或 `send_message_to_thread` 冒充新部门；固定部门仍是唯一负责人，并必须在原聊天回复、写 outbox、交 QA 和进入准确的风险放行流程。子智能体 `completed` 不满足任何主工作流回执。
16. 部门健康检查必须同时核对 `bound_and_visible`、`reply_health`、`dispatch_eligible`、项目 ID、`cwd`、侧边栏分组和交接文件。需要替补时，新窗口只有进入注册表为该角色指定的分组（运营总控进入“装修公司总控”，执行部门进入“装修公司部门”）、继承原交接文件、在同项目同 `cwd` 下产生非空可见回复并完成应用现场验证后，才能写入注册表并接替原任务。如果当前工具无法验证分组，必须保持 `blocked_replacement_requires_app_capability`，不得在项目外单开。
17. 部门现场健康证明有效期为 26 小时。过期或失败状态不得继续新派工；精确健康探针只允许发往注册表中的固定执行部门，回复后用 `department-health-record` 登记身份和回复哈希，不保存聊天正文。额度失败不自动触发替换窗口，额度恢复并产生非空可见回复后再恢复派工。
18. 模糊任务只留在运营总控并向老板补问，不默认发送付费部或 QA。全局自动任务路由由独立治理任务审计，不能放进任何装修执行部门；其总账只保存身份与提示词哈希。现有错配先隔离并等待老板批准，禁止未经批准自动暂停。
19. 常驻网站发布授权只适用于 `<WEBSITE_PROJECT_ROOT>` 与 `flashcast.com.my`，且只覆盖 `site_publish`、`cms_write` 的常规优化。每次执行 scope 必须以 `flashcast.com.my:` 开头，并由政策层生成可审计的单次精确许可。购物网站、Vendure、CloudBridge、ID 系统、Google Ads、CRM、客户联系、付款、价格/合同承诺、数据库 schema、账号权限、密钥、计费/新增费用、DNS/基础设施、硬删除和未确认业务事实均不在授权内。发布门禁失败必须停止；已发布版本公开复核失败时按既定回滚方案处理并如实报告。
20. 网站日常优化按 `playbooks/site-release-risk-boundary.md` 分级。R0 内部工作自动执行；R1 常规 CMS 内容和 R2 低影响网站代码在事实、准确 diff、必要检查、QA、备份与回滚通过后，由运营总控记录 `AUTO_RELEASE` 并使用现有常驻授权实施，不逐次请示老板。发布通道必须先二选一并由 QA 回执锁定：CMS 已有内容字段使用 `cms_content_candidate → cms_write`，只走受保护后台/`content-publish`；前端映射、渲染、Schema 或组件逻辑使用 `site_code_candidate/site_code_rework_candidate → site_publish`，只走 Git/PR/CI/main/同 SHA 部署。禁止把 CMS 内容硬编码到前端，禁止用代码部署冒充后台内容发布，通道不匹配时政策层必须拒绝。只有 R3、授权外范围或无法安全回滚的重大动作请求老板批准。QA 采用合理确认：P0 或与本次范围直接相关的 P1 才阻断；P2 记录后不阻断，最迟三个日检周期处理；GSC/GA4/销售数据缺失只阻断依赖它们的效果结论，不阻断证据充分的普通内容与技术优化。R1/R2 被 QA 阻断且返工范围明确时，`BLOCKED` 不是任务终点：QA 必须给出最小返工范围和复验条件，运营记录 `REWORK` 并指定原专业部门，原部门在下一次执行窗口优先完成最小修复、必要检查、备份和回滚包，以原 task_id 和新候选版本回交 QA。返工候选未获 QA PASS 前不得发布；同一阻断项每天最多自动尝试两次，仍失败则如实保留并汇报，不得转给无关部门或升级成无依据的老板审批。
21. 每个固定部门任务结束时，无论结果是完成、发布、未放行、返工、阻断、失败或需要输入，都必须在本部门固定聊天向老板/总控汇报实际结果，再写 outbox/report。汇报必须说明：完成了什么、产物或证据路径、是否修改或发布、实际验证结果、遗留问题、负责人和下一步；不得只回复 `completed`、`healthy`、文件链接或任务已触发。计划任务出现新完成结果、阻断、失败、回滚或需要老板处理时必须通知；只有状态没有变化且没有新产物的 `NO_CHANGE` 才可保持安静。运营总控汇总时必须区分部门交付、QA、批准、执行和生产复核，不能把其中任一阶段冒充全部完成。
22. 对 `flashcast.com.my` 的 R1/R2 常规优化，最新候选一旦同时取得 QA PASS、运营 `AUTO_RELEASE` 和政策层精确放行，内容、SEO 与网站增长部必须在当天 14:30 发布收口窗口立即按锁定通道执行，不得停在报告、PR 或“等待老板确认”。CMS 字段走后台，程序逻辑走 Git/PR/CI/main/同 SHA 部署；成功后必须公开复核并记录回执。只有 R3、授权外、无法安全回滚、缺少合法权限/OTP，或外部平台安全重试后仍失败时才停止并如实汇报。
23. 每天 15:00 由运营总控输出当天最终公司工作汇报，逐一列出运营总控和五个执行部门：是否有计划任务、是否实际运行、做了什么、产物、是否做好、QA 结论、是否发布、CMS Saved ID 或生产 SHA、线上验证、阻断、负责人和下一步；暂停或无任务也要明确写出，不得省略。网站流量分析由内容、SEO 与网站增长部每天写入网站增长日报，总控在 15:00 汇总；只使用注明日期范围且通过新鲜度检查的脱敏 GSC/GA4/销售证据，分别报告自然曝光、点击、CTR、排名/查询与页面、自然用户/会话/落地页、咨询动作及 1/7/28 日变化。没有当天可用数据时写 `DATA_MISSING`、最后可用日期和补数负责人，不得把旧数据冒充今日数据或把缺失写成 0。
24. 总控发现部门交付缺口、QA 返工或发布阻断时，必须按原 task ID 记录问题、唯一负责人、最小下一动作和复验条件，并跟进到已复验/已发布或明确的外部输入阻断，不得只咨询或转述后搁置。发送后续任务前先读取 Codex 现场状态：目标固定部门若为 `active`，普通后续任务不得插入消息或强行打断；等待当前轮次结束或进入需关注状态，再重新核对项目、固定任务、标题、目录、分组、健康状态及精确 `policy-check`，只发送一次有界的下一任务。只有老板明确要求中断，或有可证实且等待会扩大损失的 P0 安全事故，才可另行处理紧急打断。QA 对规划/候选的 PASS 不等于生产发布 PASS；通过发布门禁后按常驻授权主动执行正确的 CMS/代码通道和公开复核，缺少合法权限或认证时明确交给授权保管人恢复，不反复碰 401、不绕过保护、不伪称已上线。

## 绑定漂移与阻断恢复

- 计划任务身份核验必须优先使用 Codex `list_threads` 的现场列表，程序内只筛选本次注册表固定 task ID 的身份元数据及其所在分组，不读取其他任务正文。该接口使用 `projectId`、`id`、`title`、`cwd`；`read_thread` 用于轮次/回复检查，其响应可能没有项目 ID，不能把此接口的字段缺省单独判成跨项目。先取得完整列表身份再核验；列表仍缺字段、目标不唯一或身份不一致时继续 fail-closed。视觉音乐采集使用 `departments/visual-design-video/scripts/music_scout_preflight.py` 验证新鲜的单目标现场快照，禁止用注册表值补造现场字段。
- Codex 应用的侧边栏分组 ID 属于可轮换的运行时标识；`data/department-registry.json` 中的 `sidebar_section_id` 只能作为最近一次观察值，不能单独作为项目身份结论。每次计划任务先按准确分组名称、项目 ID、固定 task ID、标题和 `cwd` 唯一解析现场分组。
- 如果只有分组 ID 变化，而准确分组名称、项目 ID、固定 task ID、标题和 `cwd` 全部唯一匹配，执行部门必须停止本轮业务写入并回报 `STALE_SIDEBAR_BINDING`；运营总控必须在同一恢复分支更新注册表、运行精确健康探针、保存恢复证据，并使用原 task ID 安排下一窗口补跑，不得把该情况当成永久跨项目阻断。
- 运营总控每次运行必须优先处理当天或跨日的 `blocked_recovery_required`、`STALE_SIDEBAR_BINDING` 和 `verification_stale` 回执，再处理普通放行和日终汇总。恢复成功后要记录 `recovery_ready_for_retry`，并向原固定部门发一次有界补跑任务；没有恢复回执不得声称部门已继续工作。
- 分组名称不存在、出现多个同名候选、项目/任务/标题/目录任一不一致，或健康探针无法取得非空可见回复时，继续保持阻断并通知老板；不得为了让任务继续而猜测或删除绑定。

## 活跃增长工具层

第一批和第二批老 Skill 能力已经适配到 `tools/flashcast_ops.py`。涉及增长数据、Google Ads 日检、内容、SEO、复盘、备份或工作区维护时，优先读取 `tools/README.md`，按需调用：

- `source-manifest` / `conversion-reconcile` / `action-queue`
- `migrate-inputs`（仅把旧 Skill 的脱敏结构化快照填入空 active 表，并保留历史来源标记）
- `handoff` / `run-ledger` / `qa-gate` / `ads-daily`

- `content-queue` / `content-draft` / `content-qa`
- `seo-index-audit`
- `learning-record` / `department-learning-record` / `department-learning-status` / `weekly-review`
- `backup` / `change-log` / `rollback`
- `workspace-maintenance`

工具默认只读、草稿或预演。不得把历史目录当成当前事实；不得在没有人工批准的情况下使用 `rollback --apply` 或 `workspace-maintenance --apply`。工具层不登录 Google Ads、GA4、GSC、CMS 或客户账号。

## 团队路由

| 工作 | 首选 Agent |
|---|---|
| Google Ads、数据对账、转化追踪 | `付费增长与转化数据部`（固定子 Skill：`google-ads-renovation-ppc`） |
| 内容、SEO/GEO、落地页和网站转化 | `内容、SEO与网站增长部`（固定子 Skill：`renovation-seo-geo`） |
| 图片、广告视觉、装修视频、字幕和动效 | `视觉设计与视频部`（固定路由装修视频、图片生成、HyperFrames 和媒体素材方法） |
| 报价、线索分级和销售跟进 | `销售与线索部`（固定子 Skill：`renovation-sales-ops`） |
| 页面、广告和数据发布前验收 | `质检与Reality Checker部` |
| 整体协调、排期和审批 | `FLASH CAST Growth Controller` |

## 文件命名

- 日报：`reports/YYYY-MM-DD-google-ads-daily.md`
- 周报：`reports/YYYY-[W]XX-growth-review.md`
- 内容计划：`reports/YYYY-MM-content-plan.md`
- 广告实验：`reports/experiments/YYYY-MM-DD-<experiment-name>.md`

## 审批边界

默认允许：读取资料、分析数据、写方案、生成草稿、生成报告、提出代码修改建议。

默认不允许直接执行：修改广告预算、修改线上广告、发送客户消息、处理付款、承诺价格或合同条款。装修网站常规优化的内容发布和生产网站修改按常驻授权直接执行；授权外动作仍必须在报告中列为“待人工批准”。
