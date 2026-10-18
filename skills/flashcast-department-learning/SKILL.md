---
name: flashcast-department-learning
description: "按当前目标查阅有证据经验并记录完整批次复盘；默认仅加载引用索引，历史任务不作为新指令。"
---

# FLASH CAST 部门经验与引用

专业方法由注册主Skill负责，共同流程以playbooks/department-system-current.md为准。本Skill只管理工作经验与事实引用，不增加执行步骤或外部权限。

## 读取时机

首次进入项目：运行`department-learning-effective --department <部门ID> --phase startup`，读取本次所需资料。同任务续办用`--phase resume`恢复actual_current_assignment的未完处。上次视图已实际读取并保存在本任务目录时，可用`--known-rules <项目内视图.json>`，只读rule_context.sources_to_read和reference_sections_to_read。规则读取复用不复用实时权限、队列、健康或生产状态。

默认current_lessons和knowledge_reference仅列lesson_id、source_ref及新鲜度等索引。需要解决本次具体问题时，按准确source_ref或`--include-reference-details`查阅原经验。即使status=verified，某次任务的结果、当时的限制、旧next_action仍只解释原任务，不形成新的通用规则。

## 使用经验

- 事实按真实来源、日期及适用范围使用；新事实与旧资料冲突时保留冲突并核相关变化。
- 推断明确标注；缺来源的数据为DATA_MISSING或待确认，不当成0。
- 已完成且源未变的成果复用；当前数据确实过期、目标变化或原假设不成立时，才触发相应复核。
- 公司资料按当前任务相关事实读取，不因查询一条经验而重放整套初始化或历史交付。

## 完整批次后的记录

先交付真实完整结果及V2，再在有新经验时沿原department-learning-record入口记录：原task、观察、证据、结论、适用模式、status、last_verified_at、review_after、冲突或替代引用。没有新经验写no_new_learning，不制造复盘产物。

原JSON、继承记录、授权及历史证据保持原件。拟成为长期方法的经验需要明确适用条件，并统一修入现行共同规则或本岗位方法；不会仅凭一次verified记录自动进入正常执行流程。

经验读取、状态过滤和历史查询均不发消息、不产生费用、不修改外部账号。真实业务动作沿原授权和执行入口处理。详细记录格式见references/learning-schema.md。
