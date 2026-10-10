# FLASH CAST 完整目标交付与助理接续系统

现行模式为 `goal_delivery_assistant_v1`：总部给完整目标，专业主负责人沿同一任务执行到底，唯一负责助理独立验收并落实已授权常规后续，总部读结论、定新目标。角色/能力/绑定由注册表动态读取；QA1/QA2保留历史证据并退出新派工。禁止生产者自审，跨助理仅显式转给相同验收能力者。候选、自检、验收、采用、实际Save/部署、公开复核和业务结果分别记录。

现行入口：[项目规则](AGENTS.md)、[运行规则](playbooks/department-system-current.md)、[任务合同](data/task-contract.json)、[角色注册表](data/department-registry.json)。角色按注册表动态发现，QA历史角色不接新任务。

1. 总部给完整目标及唯一负责助理；专业主负责人执行到位，依赖齐全的步骤不逐段报审。
2. 部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。
3. 总部完成真实派工和负责助理责任交接后可以结束协调。负责助理在本批在途期间用 wait_threads 聚合完成事件，每次最多60秒、按固定聊天去重、保存cursor；结果到达后逐项收取、验收并落实下一实际动作。部门active时普通消息排队。队列不能唤醒已结束聊天；中断保留原task/turn/cursor，先核实际回执再恢复。保留已有每日兜底，不新建高频轮询、监控窗口或后台循环。
4. 状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。

三个助理的验收能力：助理1 SEO/GEO、内容事实双语、品牌、Maps；助理2 开发、CMS、功能、实际发布结果；助理3 付费、数据、视觉、销售。对应主Skill及本机方法路径在注册表与角色方法清单中；方法不授生产权限，禁止自审。

真实生产动作仍须准确授权来源、执行者、范围、事实/必要自检、备份与可执行回滚以及既有合法通道；CMS保存交publishing；本公司部门系统控制源码、规则与源码导出由system-development负责，装修官网代码/构建/部署交designated-development，Ads操作归付费部。助理验收不授账号权限，不绕401、issuer、单次许可或通道。老板已给付费任务的直接执行授权保持有效，不重新加入旧QA/HQ阻断链；只按原精确授权处理，不能扩大到其他Ads、费用或项目。秘密、Cookie、Token和完整客户PII不存不读出。仅系统改造任务 fc-20261010-goal-delivery-assistant-runtime-v1、fc-20261010-continuation-proof-rework-and-cms-entry-v1、fc-20261010-department-flow-audit-repair-v1 的开发交付限制为候选与迁移包，且不含网站/CMS/Ads/Maps实际写入、推送部署或平台自动化变更；该限制不扩展到其他已有准确授权的业务。平台提示词迁移由总部或已获准确授权的助理经原生工具完成，不手改automation.toml。

安装/导出只含控制源码、动态角色与空模板，聊天、账号、许可、健康、业务资料及主账不公开。已有固定ID/历史回执不得复制到新公司。Python 3.9以上标准库；真实导出入口为 `python3 tools/export_department_system.py --target <项目内导出目录>`，安装入口为 `python3 <导出目录>/tools/setup_department_system.py --root <导出目录>`。

共用 `tools/department_system_package.py` 在安装写入前核完整manifest的文件path/hash/bytes、canonical指纹、当前goal模型、退役角色和必要依赖，以及effective现有注册表/模型与全部计划目标；缺失、篡改、正向旧链或未声明旧模式拒绝且不留下半套配置。setup仍装原五配置和七份空资料，agent-role-policy示例只作验证依赖；重复安装仅创建missing，保留绑定、授权、业务数据和WIP。`flashcast_ops`启动经 `validate_startup` 验证：导出包核完整manifest，源码公司无manifest时核当前data模型/注册表。历史packet/step-a导出副本为非运行R0兼容示例，不是新goal模板；外部批准Skill须本机核验，不打包机器私有Skill，也不授权限。详见[源码导出与安装](playbooks/department-system-source-release.md)。

源码发布、真实采用与业务目标分别记录；本次系统改造无推送部署授权时不执行推送或部署，该限制不扩大到其他已有准确授权的业务。

[结果协调](playbooks/department-result-coordination.md)、[采用与恢复](playbooks/department-system-runtime-adoption.md)、[结束与事件接续](playbooks/controller-result-continuation-and-checkout.md)。当前采用状态以实际采用回执和源码回读为准，不以某批历史候选状态推断；本次差异的独立验收、实际采用与原生完成事件→助理收取→下一真实任务试点分别记录，未满足本任务完成标准时不能宣称该范围完成。

开始前用 `python3 tools/flashcast_ops.py department-learning-effective --department <注册部门ID>` 读取当前模式的只读有效学习视图。原学习JSON、继承通知和旧next_action只作历史证据；当前派工操作以现行规则和本任务真实授权为准。专业结果交唯一助理，已验收的助理总结交总部知悉，通知待发送另计；不得把总部知悉变成助理自审。

后续部门系统源码目标交system-development，唯一负责助理按development能力独立验收；装修官网源码继续交designated-development并核对该网站自己的准确授权。已派出的系统旧任务保留原task、执行者和授权，尤其fc-20261010-department-system-adopted-source-push-v18仍由原指定开发执行。本次开通任务只交候选与必要验证，不推送、部署或写外部平台；角色开通不继承其他任务许可。
