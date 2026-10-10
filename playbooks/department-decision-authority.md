# 总部与唯一负责助理的实际决策边界

现行模式为 `goal_delivery_assistant_v1`：总部给完整目标，专业主负责人沿同一任务执行到底，唯一负责助理独立验收并落实已授权常规后续，总部读结论、定新目标。角色/能力/绑定由注册表动态读取；QA1/QA2保留历史证据并退出新派工。禁止生产者自审，跨助理仅显式转给相同验收能力者。候选、自检、验收、采用、实际Save/部署、公开复核和业务结果分别记录。

总部负责完整目标、重要方向、资源冲突和授权变化。助理1能力seo_geo/content_facts/brand/maps；助理2 development/cms/functional/release_result；助理3 paid/data/visual/sales。方法路径/范围及能力同时在注册表，无能力不可转单。

负责助理可直接通过、退原负责人最小返工、安排既有批准队列下一工作、精确授权内执行接续、独立验收后关闭准确范围。参与制作者不能自己验收；转单保存显式transfer与同能力校验。助理结论交总部摘要，不加二审。

部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。

总部完成真实派工和负责助理责任交接后可以结束协调。负责助理在本批在途期间用 wait_threads 聚合完成事件，每次最多60秒、按固定聊天去重、保存cursor；结果到达后逐项收取、验收并落实下一实际动作。部门active时普通消息排队。队列不能唤醒已结束聊天；中断保留原task/turn/cursor，先核实际回执再恢复。保留已有每日兜底，不新建高频轮询、监控窗口或后台循环。

真实生产动作仍须准确授权来源、执行者、范围、事实/必要自检、备份与可执行回滚以及既有合法通道；CMS保存交publishing，代码/构建/部署交指定开发，Ads操作归付费部。助理验收不授账号权限，不绕401、issuer、单次许可或通道。老板已给付费任务的直接执行授权保持有效，不重新加入旧QA/HQ阻断链；只按原精确授权处理，不能扩大到其他Ads、费用或项目。秘密、Cookie、Token和完整客户PII不存不读出。仅系统改造任务 fc-20261010-goal-delivery-assistant-runtime-v1、fc-20261010-continuation-proof-rework-and-cms-entry-v1、fc-20261010-department-flow-audit-repair-v1 的开发交付限制为候选与迁移包，且不含网站/CMS/Ads/Maps实际写入、推送部署或平台自动化变更；该限制不扩展到其他已有准确授权的业务。平台提示词迁移由总部或已获准确授权的助理经原生工具完成，不手改automation.toml。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。
