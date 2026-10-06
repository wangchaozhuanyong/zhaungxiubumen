# 结果入队与总控并发收取

部门登记一次 notification_queued 后，总控可能在部门当轮结束前已经收取并作决策。这是正常推进，不能断言 controller_received 必须 false 或 controller_decision 必须 pending；也不能用 results[0] 或总 pending_count 判定本结果成功。

按原 task_id、sender_department、candidate_version、最终 outbox SHA-256 四项选中唯一结果，并回读同一身份的唯一 notification_queued 回执。queued、controller_received、controller_decided 三阶段都保留入队成功。结果已收取或已决策时如实报告当前阶段，不撤销总控记录、不重放通知、不重新制作候选。决策仍须关联真实后续动作，不能记为业务完成。

只读回读命令：python3 tools/result_handoff_readback.py --outbox <本项目最终冻结V2绝对路径>。这个 helper 不登记、修改、发送、派工或发布。准确队列回执缺失、身份不符或重复时保留阻断证据，由原负责人恢复；缺失不能由缓存的状态或其他结果代替。

本规则补充现有冻结方法，不改原 result-notification-key-and-recovery、短键 helper 或历史记录。新派工读本规则，旧 active 轮不插消息；下一次正式有界接续时采用。
