# 部门系统运行接口参考

本文件按场景查阅，工作流程和权限边界以[共同规则](department-system-current.md)为准。它不是每轮必跑清单，使用接口时只读取匹配章节。历史事故的讨论和取舍保留在原报告与备份。

<a id="messages"></a>
## messages：实际准备发送消息

沿原任务、版本、动作和幂等键查已有发送。正文含完整原task_id，新指派标记assignment_record_required=true。运行`goal_source_recovery.py prepare-message --input <准确消息JSON>`一次，该入口实际消费授权及policy预检。目标当前轮工作中保留待送责任；空闲放行后发送准确原文一次，记录真实原生调用、policy_decision_id、dispatch_sent和assignment-record。非空接单后记录ACK；prepared不算sent。

<a id="delivery"></a>
## delivery：完整业务批次冻结

在固定聊天声明准确结果，保存校验V2，以task_id、sender_department、candidate_version和最终outbox SHA唯一交接。结束前交接使用result_source_phase=delivery_ready，真实消息的一行FLASHCAST_DELIVERY_READY加JSON包含上述四字段、outbox_path及batch_complete:true；绑定实际thread/turn/message和原文UTF-8哈希。进度、ACK、未冻结成果各保留原身份。

真实轮次结束后用goal_continuity turn-completed补结束事件，保留冻结成果。部分/阻断批次也可完整交接，父业务剩余继续保留。漏报沿真实原件恢复，不要求重做。

<a id="acceptance"></a>
## acceptance：整批成果待验收

result-select选择合格且未参与制作的助理。唯一认领沿token/fence、1–900秒租约续租；已开始验收按显式转交恢复。核本次变化、准确原件及原标准，复用未变有效检查。controller_received/controller_decision/controller_followthrough为兼容事件名，实际角色写负责助理。

通过须落实下一动作或准确范围关闭；返工一次列清最小缺口；依赖具名并列恢复条件。助理总结到总部仅作知悉，可按实际通知或总部真实读取原生冻结结论收取，不增加技术二审。入队、发送、实际读取和后续分别记实。

<a id="target-state"></a>
## target-state：列表仅返回notLoaded

读取准确固定聊天的最新真实轮次，将原件指纹置于live_identity.actual_native_target_turns，以固定thread_id为键。选择、通知认领和发送前预检使用同一有效证明；未加载本身不证明空闲或持续忙碌。

<a id="notice-recovery"></a>
## notice-recovery：通知或执行效果不确定

保留原件，先读实际效果。秒级原生时间和本地小数秒按发送前边界、唯一新调用及接收效果关联；原文UTF-8哈希与外层文件哈希分别使用。不得补造时间或盲重发。

通知责任独立于父目标关闭保留；已真实收取的结论继续授权内后续，登记异常只暂停依赖该证明的动作。采用后事实通知使用prepare-message的post_adoption_notice，绑定唯一助理真实采用决定、后续回执、采用日志、备份和读回，原授权范围保持。

<a id="recovery"></a>
## recovery：中断、缺派工记录或来源错误

恢复actual_current_assignment及暂停目标，先核真实回复、保存、部署与送达效果，从未完处继续。新日检或消息保留旧任务位置。老板直派及历史实际发送缺本地记录时，用goal_source_recovery recover-source关联真实人类授权和原生发送；恢复记录用当前时间，不补造旧dispatch/ACK/政策。已关闭旧任务仅作来源，不授新权限。

逐条隔离assignment_errors，一条旧错误不隐藏其他有效任务。日检按完整结果身份关联原收取/决定/后续，不因后续事件未重复source_mode而重新待收。健康过期优先核原真实完成回复及原始时间；确无有效回复才沿准确健康探针恢复。来源缺失只暂停依赖它的范围。

<a id="authority-change"></a>
## authority-change：准备提出新增授权

单独用authorization-precheck解释原授权。authorization_changes仅列真实新增范围、部门、项目、账号、权限、费用/超预算、不可恢复删除、重大安全/基础设施变化。健康、绑定、回执、自检、备份及普通版本更新沿原范围修复。预检不授新许可，平台必须本人完成的验证提供准确证据、动作和保管人。

<a id="production"></a>
## production：实际保存、采用或部署

准确执行者核当前对象/字段/版本、事实、自检、原授权、备份、可执行回滚和合法通道，权限及单次消费由原入口实时校验。代码构建/CI/部署版本对应，CMS Saved ID/revision及公开内容对应。普通R1/R2授权自检执行在整批交付后验收，R3保留准确门禁。认证失败交真实保管人，验收不授账号权限。失败仍留原负责人、未完与下一动作。

<a id="finish"></a>
## finish：准备结束工作轮

同轮已取得且相关状态未变的work_boundary直接复用；需要新鲜边界时运行goal_continuity work-boundary。ready_actions先落实收取、下一动作或责任交接；仅等待具体依赖/事件时结束并保留接续。总部知悉结果已收取不再要求第二次决定。负责在途的助理在无可执行动作时集中等待原生事件，单次最多60秒并保存cursor；总部交接后处理其他目标。队列不保证唤醒已结束聊天。

<a id="daily"></a>
## daily：原日检触发

先恢复本部门真实未完目标。日检沿任务合同admitted scheduled_daily_sources记实，原排程保持。新发现归入原任务、准确新范围或明确无需动作；完整批次一次交付。无新成果、风险和待办保持安静，长期增长用真实日数据复盘，不为当轮未达50自然流量反复重查全站。

<a id="maintenance"></a>
## maintenance：原每周清理触发

只处理本项目可重建临时文件，连续7天未使用、任务结束且无有效引用均有据才进入计划；废弃中间副本按30天及隔离规则处理。正式交付、主账、授权、验收、发布、回滚、素材权利和WIP保留。先预演，执行前核路径/指纹/使用状态，不可恢复删除沿原确认边界；零候选记SKIP，不重放全部历史。
