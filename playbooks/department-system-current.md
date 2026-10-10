# 完整目标交付现行运行规则

现行模式为 `goal_delivery_assistant_v1`：总部给完整目标，专业主负责人沿同一任务执行到底，唯一负责助理独立验收并落实已授权常规后续，总部读结论、定新目标。角色/能力/绑定由注册表动态读取；QA1/QA2保留历史证据并退出新派工。禁止生产者自审，跨助理仅显式转给相同验收能力者。候选、自检、验收、采用、实际Save/部署、公开复核和业务结果分别记录。

任务输入以goal_delivery及真实human_authorization/approved_dispatch为准。目标/标准/范围/主负责人/负责助理/成果复用/依赖/能力一次明确；主负责人收回开发与发布结果，父任务不因子任务PASS关闭。

部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。

总部完成真实派工和负责助理责任交接后可以结束协调。负责助理在本批在途期间用 wait_threads 聚合完成事件，每次最多60秒、按固定聊天去重、保存cursor；结果到达后逐项收取、验收并落实下一实际动作。部门active时普通消息排队。队列不能唤醒已结束聊天；中断保留原task/turn/cursor，先核实际回执再恢复。保留已有每日兜底，不新建高频轮询、监控窗口或后台循环。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。

真实生产动作仍须准确授权来源、执行者、范围、事实/必要自检、备份与可执行回滚以及既有合法通道；CMS保存交publishing；本公司部门系统控制源码、规则与源码导出由system-development负责，装修官网代码/构建/部署交designated-development，Ads操作归付费部。助理验收不授账号权限，不绕401、issuer、单次许可或通道。老板已给付费任务的直接执行授权保持有效，不重新加入旧QA/HQ阻断链；只按原精确授权处理，不能扩大到其他Ads、费用或项目。秘密、Cookie、Token和完整客户PII不存不读出。仅系统改造任务 fc-20261010-goal-delivery-assistant-runtime-v1、fc-20261010-continuation-proof-rework-and-cms-entry-v1、fc-20261010-department-flow-audit-repair-v1 的开发交付限制为候选与迁移包，且不含网站/CMS/Ads/Maps实际写入、推送部署或平台自动化变更；该限制不扩展到其他已有准确授权的业务。平台提示词迁移由总部或已获准确授权的助理经原生工具完成，不手改automation.toml。

本轮修复前规则准确字节在 `logs/handoffs/2026-10-10-department-flow-audit-repair-v1/developer/baseline/`，同包 `lanes/rules/obsolete-current-rule-map.json` 说明退出入口。旧账缺goal按原版本可读，不能为新任务恢复QA1/QA2或预核/HQ等待。正式切换须独立新候选验收、CAS采用、真实内部完成事件与下一动作试点。

开始前用 `python3 tools/flashcast_ops.py department-learning-effective --department <注册部门ID>` 读取当前模式的只读有效学习视图。原学习JSON、继承通知和旧next_action只作历史证据；当前派工操作以现行规则和本任务真实授权为准。专业结果交唯一助理，已验收的助理总结交总部知悉，通知待发送另计；不得把总部知悉变成助理自审。

后续部门系统源码目标交system-development，唯一负责助理按development能力独立验收；装修官网源码继续交designated-development并核对该网站自己的准确授权。已派出的系统旧任务保留原task、执行者和授权，尤其fc-20261010-department-system-adopted-source-push-v18仍由原指定开发执行。本次开通任务只交候选与必要验证，不推送、部署或写外部平台；角色开通不继承其他任务许可。
