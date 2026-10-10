# 一个完整主目标与逐项真实回报

任务包带一个准确主task/candidate/action及goal_delivery；主目标可以包含多个有界子项，子task带parent_task_id，主负责人收回结果。一条消息发出或子项PASS不代表整项完成，不限制每天可执行事项数量。

现行模式为 `goal_delivery_assistant_v1`：总部给完整目标，专业主负责人沿同一任务执行到底，唯一负责助理独立验收并落实已授权常规后续，总部读结论、定新目标。角色/能力/绑定由注册表动态读取；QA1/QA2保留历史证据并退出新派工。禁止生产者自审，跨助理仅显式转给相同验收能力者。候选、自检、验收、采用、实际Save/部署、公开复核和业务结果分别记录。

部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。

总部完成真实派工和负责助理责任交接后可以结束协调。负责助理在本批在途期间用 wait_threads 聚合完成事件，每次最多60秒、按固定聊天去重、保存cursor；结果到达后逐项收取、验收并落实下一实际动作。部门active时普通消息排队。队列不能唤醒已结束聊天；中断保留原task/turn/cursor，先核实际回执再恢复。保留已有每日兜底，不新建高频轮询、监控窗口或后台循环。

遗漏沿原任务/冻结包做一次明确范围补跑，不重做未变候选、不补造原ACK，不重放已发布动作。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。
