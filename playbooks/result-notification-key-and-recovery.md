# 精确结果键与确定格式失败恢复

冻结最终V2后用只读result_handoff_key.py取得通知key；按实际helper的event/task/department/version/final SHA完整组合计算，最长200字符，不手截身份/另换顺序。不同字节或事件重新校验/计算；旧成功key和链不改，duplicate_ignored只回读。

确定输入格式拒绝保存原失败，核准确结果尚未登记、真实当前固定结果与合法来源/ACK/健康，才能仅修键/元数据登记一次。此分支不是重试CMS Save/401/部署/Ads；效果不确定先实际读回，不盲重试或重做专业成果。

专业批次真实回复、不可变结果身份、官方队列实收与原下一动作，只按唯一共同正文；保留原task/版本/SHA和SQL/native幂等，未知执行效果先读回，不重放。

新goal保留真实approved_dispatch或owner_direct引用，不补造HQ派工。原专业负责人直接完成正常实收、自检和授权下一动作；outbox_received与controller_received分别记实。历史漏记仅恢复真实元数据，不回填过去发送/时间；旧QA仍是旧事实。

状态分别为执行中、待助理验收、返工中、已完成范围、下一任务真实已安排、具体依赖等待、暂时无可执行工作。验收PASS必须关联实际下一动作或准确范围关闭；prepared不算sent，passed不算adopted，子任务结束不关闭父目标。缺输入只暂停依赖它的动作，其他独立合法工作继续。停止时列已完成、未完成、唯一负责人、下一动作、解除条件和复查时间；自然去重IP口径缺失记DATA_MISSING，AI效果未实测记NOT_MEASURED。
