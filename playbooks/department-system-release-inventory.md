# 完整源码版本功能清单

本页是 `2026.10.23.adopted-runtime-v1` 的源码清单，承接 `2026.10.22.current-rules-v2` 完整功能，不是另一套运行规则。共同流程见 [现行共同运行规则](department-system-current.md)，导出、安装与更新方法见 [源码导出与安装](department-system-source-release.md)。

| 已整合功能 | 主要入口 |
|---|---|
| 完整目标、实际当前指派、工作边界与连续接续 | `tools/goal_delivery_runtime.py`、`tools/goal_continuity.py` |
| 原授权、真实来源恢复与准确消息预检 | `tools/goal_source_recovery.py`、`tools/workflow_control.py` |
| 固定窗口轮换、完成来源与原任务保留 | `tools/department_rotation.py`、`tools/rotation_completion.py`、`tools/sales_original_assignment.py` |
| 唯一助理交付、验收计划与父目标初次接续 | `tools/result_coordination.py`、`tools/qa_review_plan.py`、`tools/parent_initial_dispatch.py` |
| 品牌执行者绑定与已采用成果的后续消费 | `tools/brand_v4_issuer_executor.py`、`tools/owner_adopted_pilot_consumer.py` |
| 付费双窗口共用专业知识、分别保留任务和回执 | `tools/setup_department_system.py`、动态注册表中的 `shared_department` |
| 视觉旁白、字幕与音画证据校验 | `departments/visual-design-video/scripts/narration_contract.py` |
| 完整源码脱敏、包完整性检查和幂等空安装 | `tools/export_department_system.py`、`tools/department_system_package.py`、`tools/setup_department_system.py` |
| 代码、CMS和系统采用的发布衔接 | [发布计划与及时接续](department-system-current.md#发布计划与及时接续) |

分发包包含动态角色定义、必要工具与项目内方法，以及五份待本地安装的配置和七份公司资料空模板。角色是否可接单由实际注册表决定；历史质检角色不恢复新派工。账号、聊天绑定、健康、真实授权、业务数据和历史回执均不随源码分发。

整合验证在隔离空安装中完成：控制与交接回归897项，另复核运行边界216项、旁白校验41项。公司专用原生证据缺失的用例分别跳过5项和2项，不能据此宣称真实业务全量检查通过。检查方法见 `ci/department-system-checks.yml.example`；重复安装不覆盖已有资料、绑定及授权。

源码整合包含两处兼容修复：未带goal标记的历史快照沿历史读取，损坏的新goal对象拒绝；原派工ACK不能代替当前专业成果依赖。它们的源码发布与本地公司运行采用分别记录。尚在制作、验收或采用中的后续候选不属于本版本已运行功能；其原任务、执行者、基线及完成标准继续保留。

源码合并、实际运行采用、网站部署、CMS保存和广告启用各自核实。本页及Git提交不替代对应真实执行回执。

本版同步当前已采用的验收前准确来源兼容，以及三文件只读协调消费者：`workflow_control.py`、`goal_delivery_runtime.py` 和 `owner_nonpayment_coordination.py`。当前运行采用已经逐文件读回并保留对应journal；公开包脱敏后仍需在本公司以外重新配置和取得真实授权，不继承本公司的执行权限。源码安装包不包含真实聊天、公司主账、账号、许可或采用回执。

完整交接拥堵优化、官方控制通道、登录自动恢复、品牌版本消费者和ChatGPT运行采用阶段仍按原任务继续；尚未采用的候选不随本版发布，也不据此宣称自动恢复、网站发布或广告开投完成。当前共同规则只从项目根目录的 `playbooks/department-system-current.md` 加载，历史导出及验证目录不作为规则入口。

本次规则清理将五个旧共同规则兼容入口退出，所有有效引用直接读取当前正文；导出工具撤下旧规则不再创建 withdrawn-source 备份，保留用户修改防覆盖检查。较后已实际采用的两回执读取修复同步到源码，四条原键恢复及正式技术PASS沿原真实回执，不重做验收。其余A2/SYS在途修复与main中的两处兼容差异，仍按各自真实采用证据判断，不因本次规则同步称全部已运行。
