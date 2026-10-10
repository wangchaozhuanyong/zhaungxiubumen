# 合法数据刷新完整批次

总部只给准确数据目标/日期窗/来源与唯一主负责人，专业制作归paid-growth-data；读取最新合法Ads/GA4与脱敏销售，先核账户/时间/币种/时区/来源新鲜度，对齐点击→咨询动作→真实询盘→有效→报价→成交。缺失不写0，历史快照不作当前；搜索词/出价只在原准确授权内行动。既有已登录/只读权限缺失列真实账号保管人，不取秘密或绕验证。

结果由未制作、具data能力的唯一负责助理验收与常规接续，总部不代做分析或二审。

部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。
