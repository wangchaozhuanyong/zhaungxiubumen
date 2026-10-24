# FLASH CAST 部门协调系统

本目录为独立Python标准库业务协调项目，非Git根目录；装修官网属于独立项目。现行模式`department_autonomous_delivery_v1`，共同流程只读[department-system-current.md](playbooks/department-system-current.md)，接口见[运行参考](playbooks/department-system-runtime-reference.md)。

专业部门独立制作、自检和完成已授权实际效果，结果直报HQ；跨专业由HQ协调并回原owner。总部助理1仅待命，助理2/3退役历史，不是运行门禁。配置见`data/department-registry.json`、`data/task-contract.json`、`data/action-policy.json`及`data/department-routing-rules.json`。

使用`python3 tools/flashcast_ops.py --help`查询原入口；恢复本部门工作使用`department-learning-effective --department <ID> --phase resume`。新目标完整合同不要求responsible_assistant；执行仍核准确授权、对象、预算期限、版本/CAS、防重复和真实读回。输出归本项目，保护并行WIP、原任务/历史回执和当前/暂停指派。

源码公开目录`releases/zhaungxiubumen`保留原Git工作区；本次内部模式迁移不授推送/部署权限。平台自动任务用第一方工具管理，不手写平台TOML。历史包不是现行规则；旧规则清理按准确清单执行。
