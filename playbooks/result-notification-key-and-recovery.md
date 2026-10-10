# 精确结果键与确定格式失败恢复

冻结最终V2后用只读result_handoff_key.py取得通知key；按实际helper的event/task/department/version/final SHA完整组合计算，最长200字符，不手截身份/另换顺序。不同字节或事件重新校验/计算；旧成功key和链不改，duplicate_ignored只回读。

确定输入格式拒绝保存原失败，核准确结果尚未登记、真实当前固定结果与合法来源/ACK/健康，才能仅修键/元数据登记一次。此分支不是重试CMS Save/401/部署/Ads；效果不确定先实际读回，不盲重试或重做专业成果。

部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。

新goal的来源可为真实approved_dispatch或owner_direct引用，不能补造HQ派工。负责助理按准确token/fence/能力收取和独立验收，outbox_received与controller_received分别记录；发现历史漏记只按当前真实来源补元数据，不能假造过去发送/时间。已采用源码另存新hash和实际检查，旧QA证据保留为旧事实。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。
