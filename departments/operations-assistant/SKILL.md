---
name: flashcast-routine-coordination
description: HQ与总助理共用的普通结果收取、决定、协作接续及直接回复方法。
---

# 普通协调与决定

共同流程只按[唯一正文](../../playbooks/department-system-current.md)。按当前真实老板委托由总助理优先独立决定和接续，HQ处理需其决策的事项并补位；普通确认不回推老板。授权来源、准确范围及具体平台/资料依赖统一按共同正文核验。专业部门保留制作、自检和已授权执行责任，不增加逐步技术审核。

用`python3 tools/chief_assistant_coordination.py authority`读取真实新委托。对准确task/sender/version/SHA先查原队列、SQL/native实收及未知效果。旧logical_receiver不改，coordinator_role/coordinator_owner写自己的真实角色与固定聊天。首次未收才沿`result_coordination.py claim`的同结果token/fence与1..900秒租约领取；HQ和助理不能同时处理。已有controller_received时直接复用原实收，作新普通决定使用`CoordinationStore.claim_decision`的仅决定租约，不能重领收取或重收；准确方法见[已实收后的普通决定与回传](../../playbooks/department-system-runtime-reference.md#已实收后的普通决定与回传)。

实际阅读完整原件后，自己的真实native回复须含准确SHA；沿正常`workflow_control.record_result_handoff(controller_received)`提交，附routine_delegation、logical_receiver和实际领取。不代签HQ或其他部门，不编ACK/完成final。然后冻结`routine-original-result-decision/v1`：绑定同身份、原outbox、scope、原owner/下一动作与真实委托，自己的真实回复钉住决定path/SHA；正常controller_decision记录普通决定。

普通决定只允许继续原owner、确认已完成范围、原scope内协调、具名等待或升级敏感项；不签发/消费生产许可，不扩账号/预算/期限/项目，不伪造qa_verdict/PASS或关闭业务父目标。完成专业检查由原owner负责，决定不等于发布/保存实效。

直接回复用`chief_assistant_coordination.py reply --input <准确request> --directory <本项目logs/handoffs目录>`；request的routine_decision_reply绑定原身份和decision_record_id，正文钉住原resultSHA及决定path/SHA。正常prepare/policy后先持久唯一意图，再一次官方queue；未知/断线先`reply-effect`读原键，不能重发。accepted不等于received，原owner真实ACK/下一动作再读回。普通收口不逐件回HQ再审。已登记决定还须实际回传原next_owner；只写下一负责人或未来检查时间不是已派工。先核该decision_record_id的所有原reply意图，再正常运输一次；缺准确输入则只登记该依赖，不能用状态文件代造正常followthrough。
