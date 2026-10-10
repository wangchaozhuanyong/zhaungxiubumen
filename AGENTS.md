# FLASH CAST 部门系统现行规则（完整目标交付）

现行模式为 `goal_delivery_assistant_v1`：总部给完整目标，专业主负责人沿同一任务执行到底，唯一负责助理独立验收并落实已授权常规后续，总部读结论、定新目标。角色/能力/绑定由注册表动态读取；QA1/QA2保留历史证据并退出新派工。禁止生产者自审，跨助理仅显式转给相同验收能力者。候选、自检、验收、采用、实际Save/部署、公开复核和业务结果分别记录。

本目录是 `<PROJECT_ROOT>` 的业务协调系统，官网代码属于独立网站项目。所有候选、日志、备份和输出先确认所属项目及绝对路径。保护并行WIP，按精确diff/CAS采用，不覆盖整目录、业务主账、聊天健康或历史回执。

1. 开始读取本目录README、注册表、任务合同、动作/委派政策、公司七份确认资料及本部门主Skill/学习。不得猜公司案例、资质、价格、客户/广告数据。专业方法按注册表白名单，助理方法仅独立验收用途。
2. 完整任务 `goal_delivery` 一次写目标、完成标准、主负责人、负责助理、已有成果、授权范围、协作依赖、生产部门和验收能力，子任务带父引用。老板直接任务保留真实 human_authorization，不补造HQ派工。缺goal的旧账仍可读，不制造新通过记录。
3. 总部只定目标/优先级/资源和重要授权变化，不做专业制作或代码实现。唯一助理按对应能力验收、最小返工、既有范围接续与准确关闭；总部不二审。新方向/授权外才交总部。动态新增岗位须能力、技能、路由、真实绑定和回报入口齐全，不能按固定部门数量判断。
4. 每项结果只交一个未参与制作的负责助理。三个助理并行，不串行全量复查；能力不足不可转单。QA1/QA2不接新派工或例行任务，旧PASS/许可仅保留原准确历史。
5. 部门先在原固定聊天非空回报，再冻结并校验V2；按 task_id、sender_department、candidate_version、最终outbox SHA-256 唯一入队。V2保留顶层 fixed_chat_task_id、chat_reply.nonempty 和 in_current_fixed_department_chat 的真实证明，准确原消息UTF-8字节计算哈希，不以ACK替结果。负责助理用既有事务认领、token/fence、1–900秒租约及续租处理；一个结果一个有效处理人。不确定发送/保存/部署先回读真实效果，缺效果须显式恢复后才能重试。controller_received/controller_decision/controller_followthrough 是兼容事件名，实际主体写助理身份，不能冒充总部。
6. 总部完成真实派工和负责助理责任交接后可以结束协调。负责助理在本批在途期间用 wait_threads 聚合完成事件，每次最多60秒、按固定聊天去重、保存cursor；结果到达后逐项收取、验收并落实下一实际动作。部门active时普通消息排队。队列不能唤醒已结束聊天；中断保留原task/turn/cursor，先核实际回执再恢复。保留已有每日兜底，不新建高频轮询、监控窗口或后台循环。
7. 真实生产动作仍须准确授权来源、执行者、范围、事实/必要自检、备份与可执行回滚以及既有合法通道；CMS保存交publishing，代码/构建/部署交指定开发，Ads操作归付费部。助理验收不授账号权限，不绕401、issuer、单次许可或通道。老板已给付费任务的直接执行授权保持有效，不重新加入旧QA/HQ阻断链；只按原精确授权处理，不能扩大到其他Ads、费用或项目。秘密、Cookie、Token和完整客户PII不存不读出。仅系统改造任务 fc-20261010-goal-delivery-assistant-runtime-v1、fc-20261010-continuation-proof-rework-and-cms-entry-v1、fc-20261010-department-flow-audit-repair-v1 的开发交付限制为候选与迁移包，且不含网站/CMS/Ads/Maps实际写入、推送部署或平台自动化变更；该限制不扩展到其他已有准确授权的业务。平台提示词迁移由总部或已获准确授权的助理经原生工具完成，不手改automation.toml。
8. 状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。

采用状态须有独立验收、准确CAS采用和真实内部原生完成事件→助理收取→下一实际任务试点。本包 candidate 未采用时不能称系统已切换；平台自动任务仅由总部或采用后有权助理经原生工具更新，开发只交提示词迁移表，不手改automation.toml。

本轮修复前规则的准确字节保存在 `logs/handoffs/2026-10-10-department-flow-audit-repair-v1/developer/baseline/`，变更对应见该包 `lanes/rules/obsolete-current-rule-map.json`；其他历史包保持原样。现行入口读取本文件与playbooks/department-system-current.md，不恢复旧QA/预核/HQ等待链。

开始前用 `python3 tools/flashcast_ops.py department-learning-effective --department <注册部门ID>` 读取当前模式的只读有效学习视图。原学习JSON、继承通知和旧next_action只作历史证据；当前派工操作以现行规则和本任务真实授权为准。专业结果交唯一助理，已验收的助理总结交总部知悉，通知待发送另计；不得把总部知悉变成助理自审。
