# 完整目标中断与准确恢复

新goal读取唯一负责助理、原任务/父引用、准确候选与结果哈希；旧账缺goal按原事件解释，不把旧QA或批准补作新版本。

固定聊天现场核project/title/task/cwd/分组与26小时非空回复健康；过期不改成今天。不因read_thread/wait_threads输出空就断言真实空回复，必要时只读核同一task/cwd/最新turn/session的实际final与task_complete，输出ID/时间/hash，不读秘密或其他项目。真实轮次额度/临时错误才登记该轮失败，不把旧失败当当前状态。

仅分组ID漂移而准确名称/项目/聊天/title/cwd唯一一致，记录原值/现场值和恢复原因，由已有合法健康恢复入口处理；不凭candidate文件更新活跃健康或创建替补。身份歧义或权限缺失保留具名阻断，恢复不代表业务完成。

消息工具isError/明确失败不记sent；notLoaded/thread-not-found只读核原固定窗口并按安全范围一次恢复，仍失败给真实原因，不另建聊天。发送不确定先读实际消息/回执；真实成功再记dispatch_sent/ACK/outbox，不能伪造历史。已完成专业候选只补必要交接元数据。

证据hash变化先核真实原字节/不可变备份，以原部门追加evidence_replacement或evidence_archive并准确引用旧receipt、path/hash/size；保留旧链，不重算、不把滚动主账当旧证据。新结果用新version/hash，不重新入队已收结果。

部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。

总部完成真实派工和负责助理责任交接后可以结束协调。负责助理在本批在途期间用 wait_threads 聚合完成事件，每次最多60秒、按固定聊天去重、保存cursor；结果到达后逐项收取、验收并落实下一实际动作。部门active时普通消息排队。队列不能唤醒已结束聊天；中断保留原task/turn/cursor，先核实际回执再恢复。保留已有每日兜底，不新建高频轮询、监控窗口或后台循环。

SQLite claim续租/显式过期恢复/移交推进fence；uncertain效果先读实际原生record，再明确恢复未追加effect，不盲重派/Save/部署。代码回滚仅本次精确CAS备份，保留新真实账、队列和业务数据；SQLite用备份接口，不能删库清占用。子智能体结果不能代固定聊天/真实验收/许可。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。
真实生产动作仍须准确授权来源、执行者、范围、事实/必要自检、备份与可执行回滚以及既有合法通道；CMS保存交publishing，代码/构建/部署交指定开发，Ads操作归付费部。助理验收不授账号权限，不绕401、issuer、单次许可或通道。老板已给付费任务的直接执行授权保持有效，不重新加入旧QA/HQ阻断链；只按原精确授权处理，不能扩大到其他Ads、费用或项目。秘密、Cookie、Token和完整客户PII不存不读出。仅系统改造任务 fc-20261010-goal-delivery-assistant-runtime-v1、fc-20261010-continuation-proof-rework-and-cms-entry-v1、fc-20261010-department-flow-audit-repair-v1 的开发交付限制为候选与迁移包，且不含网站/CMS/Ads/Maps实际写入、推送部署或平台自动化变更；该限制不扩展到其他已有准确授权的业务。平台提示词迁移由总部或已获准确授权的助理经原生工具完成，不手改automation.toml。
