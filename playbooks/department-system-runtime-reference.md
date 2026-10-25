# 部门系统运行接口参考

共同行为只按[唯一现行正文](department-system-current.md)，本页只列现有接口。

## messages

正常prepare-message沿原task/scope、真实固定身份、原授权及完整payload；专业部门直报operations和协作回原owner。

## delivery

正常完整outbox/READY与官方result queue；notification_queued仅运输待办，controller_received要求真实接收原生及SQL/native一致。

## acceptance

普通目标由专业owner自检与实际效果读回，无助理QA。历史qa_verdict仅按原冻结来源读取。

## production

原有权执行者即时鲜读、准确任务请求、自检、版本/CAS、备份/回滚、幂等和真实结果。敏感新增事项单独报HQ。

## recovery

先核已发生效果和原幂等键；中断不伪造completed。保留原当前/暂停位置，普通恢复不换生产者。

## finish

dispatch-plan --goal；receipt-record实际派送/ACK；`python3 tools/goal_delivery_runtime.py completion-evidence-record`登记真实证明；`python3 tools/goal_delivery_runtime.py status --task-id <原task>`读回。证明schema为department-autonomous-actual-effect/v1。

## daily

既有专业排程及HQ18:00兜底保持；无变化静默，不新建轮询。

## maintenance

仅准确授权的本项目专业维护。原flash-cast-20-00的当前状态、专业执行绑定和检查范围沿maintenance-preflight实时读取；激活、真实排程运行与清理效果分别记实，历史A3许可不继承，预检不执行删除。

## target-state

忙窗口不插话，notLoaded不把accepted当启动；由原HQ第一方读取状态后一次合法恢复。

## notice-recovery

先读运输及实收；未知效果不盲重发，单事件异常隔离。

## authority-change

真实老板新授权改变模式，原合同/业务权限不扩大。


维护接线读回：`python3 tools/department_autonomy.py maintenance-preflight`。原flash-cast-20-00由SYS承接本项目检查，平台状态和绑定以准确实际读回为准；该命令不清理文件、不继承A3许可。实际清理仍须准确使用/引用、任务结束事实、精确清单和当前授权，不可恢复范围另向老板确认。
