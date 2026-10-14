# FLASH CAST 部门系统

本项目采用 `goal_delivery_assistant_v1`。唯一共同运行规则是 [department-system-current.md](playbooks/department-system-current.md)；[AGENTS.md](AGENTS.md)说明项目隔离、启动与事实资料，本文件说明配置及安装导出。共同流程不在多个入口重复维护。

当前角色、固定聊天、技能和能力从 [注册表](data/department-registry.json)动态读取；任务采用 [任务合同](data/task-contract.json)、[路由](data/department-routing-rules.json)及准确动作/委派政策。不要用固定角色数量、缓存健康或旧学习推断实际状态。

公司七份确认资料：company-context.md、service-area.md、services-and-pricing.md、customer-personas.md、brand-guidelines.md、case-studies.md、faq.md。资料中待确认的事实保持待确认，正式证据与老板实际补充沿原引用使用，不能当成已发布成果。

开始工作读取本部门主 Skill，并运行一次当前有效学习视图：

`python3 tools/flashcast_ops.py department-learning-effective --department <注册部门ID>`

当前学习视图提供授权预检入口；提出重复授权问题前先核原目标。`python3 tools/goal_delivery_runtime.py authorization-precheck --task-id <原任务ID> --input <准确动作JSON>` 只读解释范围，不能替代发送或生产许可。实际消息通过 `goal_source_recovery.py prepare-message` 同时消费授权及精确policy-check；现代任务普通消息的policy入口也强制消费授权预检。老板直派或历史实际发送恢复使用该工具的 `recover-source`，不补造旧dispatch/ACK。具体规则只维护在共同正文中。

## 源码导出与安装

运行环境为 Python 3.9以上标准库。本项目业务协调目录不是 Git 根目录；源码仓库、官网和业务输出各自隔离。

导出仅含控制源码、可公开的动态角色定义和空模板。密码、私人聊天、真实账号绑定、生产许可、健康、业务资料及主账不公开；当前公司固定ID和历史回执不能复制给新公司。

- 导出：`python3 tools/export_department_system.py --target <项目内导出目录>`
- 安装：`python3 <导出目录>/tools/setup_department_system.py --root <导出目录>`

`department_system_package` 在安装写入前校验完整 manifest 的 path/hash/bytes、canonical 指纹、当前goal模型、退役角色、必要依赖及有效注册表。缺失、篡改或未声明旧模式应拒绝，不能留下半套配置。首次安装只创建缺失的五配置和七份空资料；重复安装保留已有绑定、授权、业务数据和WIP，agent-role-policy 示例仅为验证依赖。源码公司无manifest时按现有启动入口核当前data模型/注册表。

历史 packet/step-a 导出副本是非运行R0兼容示例，不是新goal模板。外部方法需本机核验，不打包机器私有Skill或继承账号权限。详见 [源码导出与安装](playbooks/department-system-source-release.md)。源码导出、实际采用、远端推送和业务发布分别记录，不能凭候选或本地检查宣称上线。

结果、恢复、停止与清理统一按共同正文执行。其他历史playbook仅在准确旧任务兼容范围内追溯，不能恢复旧QA、总部二审或守候链。现行入口更新不改写历史授权、回执或正式交付证据。
