# FLASH CAST 项目入口

本目录 `<PROJECT_ROOT>` 是独立的业务协调与部门系统；装修官网源码属于独立网站项目。本项目不是 Git 根目录，源码仓库按本任务实际位置单独核对。

现行模式为 `goal_delivery_assistant_v1`。开始工作读取唯一共同规则正文 [department-system-current.md](playbooks/department-system-current.md)；本文不复制另一套共同流程。历史包、旧学习和未采用候选不作为新任务指令。

首次进入项目时读取README、当前注册表/合同/政策、本部门主Skill和必要公司资料；同任务续办按共同规则的读取时机直接恢复未完处，已读且未变的资料复用。公司七份确认资料为company-context.md、service-area.md、services-and-pricing.md、customer-personas.md、brand-guidelines.md、case-studies.md、faq.md；对外事实使用本次相关的真实确认与来源。

用一次只读有效学习入口读取本部门当前视图：

`python3 tools/flashcast_ops.py department-learning-effective --department <注册部门ID> --phase startup`

续办使用`--phase resume`；上次实际读取的视图可用`--known-rules <项目内视图.json>`识别变化。按rule_context.sources_to_read读取相关正文；实时指派、队列、权限和发布状态仍由原入口核验。

专业方法按注册表白名单；助理验收方法不得用于生产者自审。原学习JSON和旧 next_action 只供追溯。涉及固定聊天通信时，按当前注册表与实际项目、聊天、标题、目录、分组、健康和精确动作许可核对，真实发送与回报后记录，保护原任务和幂等性。

跨任务通信仅限老板明确指定并要求发送的准确目标；同原目标普通返工及接续的持续授权、逐次精确预检和升级边界统一见 [同原目标的持续授权](playbooks/department-system-current.md#同原目标的持续授权)，不把普通版本更新或发送次数当成重新批准要求。

所有可控输出、候选、日志、截图和备份归本项目；先确认绝对路径，不能散落桌面或混入其他项目。保护并行WIP，按准确差异/CAS写入，不覆盖整目录、唯一业务主账、聊天健康或历史回执。只修改当前授权范围，不因旧任务失败重做已验收范围。

总部负责目标、优先级、资源和重要授权；专业制作、代码、后台发布由对口部门执行，唯一助理负责一次独立验收与常规接续，具体职责、通知及生产边界统一按共同正文执行。

无准确任务授权不得推送GitHub、部署、修改账号或产生费用。角色开通不继承其他任务许可；已派旧任务保留原执行者及授权，不能凭新岗位替换原历史记录。准确已获授权的业务不因旧候选限制被重新阻断。
