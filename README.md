# FLASH CAST 部门系统

本项目采用 `goal_delivery_assistant_v1`。唯一共同运行规则是 [department-system-current.md](playbooks/department-system-current.md)；[AGENTS.md](AGENTS.md)说明项目隔离、启动与事实资料，本文件说明配置及安装导出。共同流程不在多个入口重复维护。

当前角色、固定聊天、技能和能力从 [注册表](data/department-registry.json)动态读取；任务采用 [任务合同](data/task-contract.json)、[路由](data/department-routing-rules.json)及准确动作/委派政策。不要用固定角色数量、缓存健康或旧学习推断实际状态。

公司七份确认资料：company-context.md、service-area.md、services-and-pricing.md、customer-personas.md、brand-guidelines.md、case-studies.md、faq.md。资料中待确认的事实保持待确认，正式证据与老板实际补充沿原引用使用，不能当成已发布成果。

首次进入项目读取本部门主Skill并运行一次当前视图；后续按实际阶段恢复任务和读取变化：

`python3 tools/flashcast_ops.py department-learning-effective --department <注册部门ID> --phase startup`

续办使用`--phase resume`，已有视图可传`--known-rules <项目内视图.json>`，仅加载变化的规则正文。历史经验默认引用索引，需要原文时用`--include-reference-details`；规则读取复用不缓存权限。

正常派工只用goal_source_recovery.py prepare-message，它已包含原授权和准确policy检查。范围不清或准备提出新增授权时再单独使用authorization-precheck；来源恢复只在缺真实绑定时使用recover-source。接口细节按[运行参考](playbooks/department-system-runtime-reference.md)对应章节查阅。

## 发布接续

代码与后台的职责、提前规划、依赖顺序、及时执行、阻断修复及真实关闭，只按 [发布计划与及时接续](playbooks/department-system-current.md#发布计划与及时接续) 执行。发布部跟进两条线，代码由原指定开发部署、CMS由发布部保存；各可独立批次推进，不等待无关任务。旧决策、审批矩阵与网站发布入口退出，调用直接指向现行正文；旧规则不另作备份。

## 源码导出与安装

当前完整源码的功能、验证范围及运行采用边界见 [版本功能清单](playbooks/department-system-release-inventory.md)。

运行环境为 Python 3.9以上标准库。本项目业务协调目录不是 Git 根目录；源码仓库、官网和业务输出各自隔离。

导出仅含控制源码、可公开的动态角色定义和空模板。密码、私人聊天、真实账号绑定、生产许可、健康、业务资料及主账不公开；当前公司固定ID和历史回执不能复制给新公司。

- 导出：`python3 tools/export_department_system.py --target <项目内导出目录>`
- 安装：`python3 <导出目录>/tools/setup_department_system.py --root <导出目录>`

`department_system_package` 在安装写入前校验完整 manifest 的 path/hash/bytes、canonical 指纹、当前goal模型、退役角色、必要依赖及有效注册表。缺失、篡改或未声明旧模式应拒绝，不能留下半套配置。首次安装只创建缺失的五配置和七份空资料；重复安装保留已有绑定、授权、业务数据和WIP，agent-role-policy 示例仅为验证依赖。源码公司无manifest时按现有启动入口核当前data模型/注册表。

历史 packet/step-a 导出副本是非运行R0兼容示例，不是新goal模板。外部方法需本机核验，不打包机器私有Skill或继承账号权限。详见 [源码导出与安装](playbooks/department-system-source-release.md)。源码导出、实际采用、远端推送和业务发布分别记录，不能凭候选或本地检查宣称上线。

结果、恢复、停止与清理统一按共同正文执行。本地从本项目根目录加载现行工具和规则，不从历史导出、验证副本或备份加载旧规则；专业方法按当前注册表读取。真实旧任务授权与回执按准确来源追溯，不能恢复旧QA、总部二审或守候链。现行入口更新不改写历史授权、回执或正式交付证据。

## 交付事件接续试点

[事件接续程序](playbooks/department-event-dispatcher-pilot.md)已接通应用自带的官方消息队列，实际启动原助理2、3并完成两份原成果收取。当前登录会话使用项目后台事件进程；激活后的完整目标及合同准入日检结果沿原来源、路由和通知许可接续，两份指定旧成果单独恢复，其他旧来源不自动重放。日检路径已通过隔离检查，重启电脑后的自启动仍未接通。队列接受不等于收取、验收或发布，原有每日兜底与各部门权限保留。
