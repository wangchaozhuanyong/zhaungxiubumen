# 运行接口索引

唯一规则见[现行正文](department-system-current.md)。

| 范围 | 原入口 |
|---|---|
| 普通建单/执行/完成 | flashcast_ops.py、workflow_control.py、goal_delivery_runtime.py、department_autonomy.py |
| 真实结果/事件接续 | result_coordination.py、department_event_dispatcher.py、goal_continuity.py |
| 历史QA/窗口来源 | qa_review_plan.py、department_rotation.py、goal_source_recovery.py，只读原事实 |
| 脱敏导出与安装 | export_department_system.py、setup_department_system.py、department_system_package.py |

源码采用不等于网站/广告执行；平台启动未验证不报自动化完成。
