# 部门系统源码发布参考

现行runtime_model为`department_autonomous_delivery_v1`。共同规则只按[唯一正文](department-system-current.md)。由system-development独立制作、自检、准确逐文件CAS采用、备份/journal/回滚和实际入口读回，完整回报HQ，无助理审批。脱敏导出沿原export_department_system.py，保护现有10项portable tests及仓库WIP，不从main覆盖本地新采用源。公开包不携带原生授权、账号、健康、许可或业务主账；安装不继承本项目权限。Git推送/部署按原任务准确授权执行，分别记录本地检查、真实推送和远端读回；源码同步不代表业务发布。历史旧包声明只读兼容。
