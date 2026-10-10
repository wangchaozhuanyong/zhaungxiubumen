# 部门系统源码导出与安装

只导出本系统控制源码、动态角色/空模板与项目自有方法。公司事实用空白模板；账号、聊天绑定/健康、真实许可、data/logs/reports/drafts、客户数据、素材和学习历史不公开，不复制本公司ID、许可或历史PASS。外部批准Skill保留路径声明，新公司须本机实际核验，不打包机器私有Skill，不因此取得生产权限。角色按注册表动态发现，不按固定11/13角色判断。

真实导出入口为 `python3 tools/export_department_system.py --target <项目内导出目录>`；真实安装入口为 `python3 <导出目录>/tools/setup_department_system.py --root <导出目录>`。共用 `tools/department_system_package.py` 验证最终包：manifest的schema_version为 `department-system-package-v1`，每项path/release_sha256/bytes对应实际发布字节，source_sha256保留来源，fingerprint核canonical无fingerprint字段JSON的SHA-256。该指纹证明输入一致性，不是可信签名或授权。缺失、篡改、不安全路径、正向旧QA/HQ链或未声明旧模式须拒绝，不能重新成为默认运行规则。

默认runtime_model必须为 `goal_delivery_assistant_v1`，`qa`/`qa-technical`退出新派工；动态注册角色的role_config、professional_skill、department_readme三份源码及批准的项目内方法须齐全，路由与必要依赖按现行规则验证。安装仍只采用原五配置：department-registry、department-routing-rules、task-contract、action-policy、delegation-policy；agent-role-policy示例是验证依赖，不新增第六个安装配置。七份公司资料使用空模板。

安装写入前验证完整静态包与effective当前注册表、模型及全部计划目标；缺失或非法输入不得留下半套配置。重复安装仅创建missing，保留已有绑定、授权、业务数据、历史和WIP。新安装所有窗口unbound/不可派工，生产权为空。`flashcast_ops`启动调用共用 `validate_startup`：导出安装包核完整manifest，源码公司无manifest时核当前data模型/注册表。历史旧task可读，不作为当前默认模型；导出副本中的packet/step-a明确标作历史R0解析兼容、非运行输入，原示例不删，也不作为安装五配置或新goal模板。

升级交准确候选diff/CAS、备份回滚与必要检查，唯一具备对应能力且未参与制作的负责助理独立验收并按已有准确授权采用，保留运行主账和新真实回执；采用后回读实际入口并完成真实下一任务试点。原生自动任务只处理真正新增迁移差异，由有权总部/助理经原生工具实际更新，不手改平台文件。

本次系统改造只交候选与最小迁移包，不执行未授权GitHub推送或部署；该限制不扩大到其他已有准确授权的业务。源码导出、空安装、实际采用、原生接续试点和业务完成分别记录。旧GitHub流程及旧task作为历史保留，不恢复旧QA/HQ/老板逐段审批链。
