# 工作流恢复接口与证据方法

共同流程、职责和继续执行标准只按[唯一正文](department-system-current.md)。本文件只说明身份、来源、错误与SQLite/CAS恢复方法。

新goal读取原专业主负责人、原任务/父引用、准确候选与结果哈希；旧账缺goal按原事件解释，不把旧QA或批准补作新版本。

固定聊天现场核project/title/task/cwd/分组与26小时非空回复健康；过期不改成今天。不因read_thread/wait_threads输出空就断言真实空回复，必要时只读核同一task/cwd/最新turn/session的实际final与task_complete，输出ID/时间/hash，不读秘密或其他项目。真实轮次额度/临时错误才登记该轮失败，不把旧失败当当前状态。

仅分组ID漂移而准确名称/项目/聊天/title/cwd唯一一致，记录原值/现场值和恢复原因，由已有合法健康恢复入口处理；不凭candidate文件更新活跃健康或创建替补。身份歧义或权限缺失保留具名阻断，恢复不代表业务完成。

消息工具isError/明确失败不记sent；notLoaded/thread-not-found只读核原固定窗口并按安全范围一次恢复，仍失败给真实原因，不另建聊天。发送不确定先读实际消息/回执；真实成功再记dispatch_sent/ACK/outbox，不能伪造历史。已完成专业候选只补必要交接元数据。

证据hash变化先核真实原字节/不可变备份，以原部门追加evidence_replacement或evidence_archive并准确引用旧receipt、path/hash/size；保留旧链，不重算、不把滚动主账当旧证据。新结果用新version/hash，不重新入队已收结果。

SQLite claim续租/显式过期恢复/移交推进fence；uncertain效果先读实际原生record，再明确恢复未追加effect，不盲重派/Save/部署。代码回滚仅本次精确CAS备份，保留新真实账、队列和业务数据；SQLite用备份接口，不能删库清占用。子智能体结果不能代固定聊天/真实验收/许可。
