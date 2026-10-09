# developer-delivery-v2 使用入口

本地候选，未采用。所有真实grant、清理准入及新排程仍关闭。采用前核对冻结manifest、当前源指纹、独立固定QA和保护配置；只应用准确diff，不能整体复制data或覆盖并行任务。

- persistent pause/resume：tools/human_control.py；实际人类来源和CAS版本必须准确。
- 三助理领取、唯一决策与中断恢复：tools/result_coordination.py。正式准入后按data/action-policy.json.department_system_upgrade.result_grants中的完整原结果键分配；未放行结果和重大例外交总部。
- 常规消息：tools/routine_grants.py validate/reserve-route/commit-route。准确原生发送回读后登记dispatch_sent；chat_ack会释放原短租约并保存真实下一负责人。未知发送不重放，token/角色仅本地审计。
- 精确内部关闭、R1/R2代理AUTO_RELEASE：tools/routine_authority.py。候选、当前独立QA和facts/diff/checks/backup/rollback/channel/version全部冻结、现有机器政策放行才安排；没有保存或部署行为、不消费许可。R3/Ads/Maps/费用/账号和扩大范围拒绝。
- 老板直接派工：tools/owner_direct_intake.py。保留真实人类消息引用、准确范围、时间和固定执行者，不保存聊天正文，不造总部派工/ACK。真实V2结果唯一入队后prepare_review把原任务纳入QA1；外部开发必须绑定原授权桥接、真实发送及其原生policy决定。
- 开发桥接只读候选审核：tools/developer_bridge.py --root <项目> --request <冻结请求> --live <原生快照>。审核不要求提前激活/发送；实际发送仍需准确当前请求的独立R0控制QA和真实空闲/分组，不按版本号或Pinned名称放行。
- 清理：tools/safe_cleanup.py先scan，冻结准确计划。execute须cleanup_admitted、独立采用、助理3准确cleanup grant、当次独立QA、当前租约和最新引用/使用/任务结束证明。旧workspace-maintenance --owner-approved不能绕过。purge先锚定目录、原子移入独占临时位置并复核，保护并行替换；中断只readback，不重放旧journal。隔离不算释放空间，物理可归因空间无法证明时NOT_MEASURED。
- 注册表新增角色自动进入源码导出和setup学习入口，仍须固定身份、专业Skill/子Skill、健康、准确路由和正式准入。候选快照data/department-registry.json不属于可应用修改。

本地测试结果不能签独立QA。正式发布部R1保存、外部指定开发执行、真实内部试点、自动化提示词采用及每周日20:00清理启用仍由原流程验收；本交付没有推送、部署、创建排程或真实清理。
