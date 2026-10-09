# V13 准确采用与恢复

本版是原任务 fc-20261008-department-system-upgrade-v1 的隔离候选。独立 QA、总部采用、真实 R0 试点、导出推送和生产执行分别记录。候选尚未发生这些步骤。

1. 独立 QA 读取 DELIVERY-MANIFEST、准确源树 SHA、同版代码差异及本地受影响检查。QA 原生固定身份、派工/ACK/outbox/verdict 与准确候选全部对应；不使用旧版本 PASS。
2. 总部逐项读回活动 before hash，按 ADOPTION-SCOPE 做文件 CAS。AGENTS、当前规则、专业 Skill/README、模板、合同、原生消费者及必要依赖一起迁移。现行付费规则和并行 WIP 保留；历史、账户、主账、原生许可、聊天、学习事件及缺失字节不被候选覆盖。
3. 注册表仅追加经现场独立核验的关联开发角色并字段 CAS；保留真实不同项目/cwd/title，不整表复制健康。学习注册仅追加缺少的角色，不覆盖现有记忆。计数重新从 departments 派生。
4. 准入记录引用准确 adoption pin、candidate pin、独立 QA outbox/receipt 及同 QA 结果的 `controller_decision_record_id`。该原生 decision 必须 operations、close_scope、QA pass、准确 acceptance_scope，并含候选及 QA pins。仅设置 admitted=true、放 role 文件或 QA PASS 均不够。
5. 三助理 grant 明确 R0/R1/R2、原 task/producer/candidate/hash/scope、事件、下一 owner、链接 task、当前 human revision、有效期、原生身份；一份结果只有一个短租约。R3/未知不发 grant，CMS 旧执行许可不转移。
6. 运行采用后沿同原任务做真实 R0 pilot，记录专业执行→冻结→入队→原助理消费者决策/QA或下一步的真实 pins。合成测试没有试点效力。没有 native 自动唤醒能力；空 hooks 保留，18:00 原兜底不另加高频排程。
7. independent QA、采用与真实 R0 pilot 都准入后，本固定开发聊天才能沿原任务调用 `adopted_system_export.prepare_adopted` 从完整已采用文件清单导出；完整代码/方法指纹必须与同候选 export_source_files 一致，运行绑定和政策快照另经采用后准确独立 source QA 绑定，真实试点 outbox 必须带同版 system_candidate_sha256/system_candidate_version、applied_source输入及采用后执行时间，再导出到项目内 releases/zhaungxiubumen，未来授权仓库为 wangchaozhuanyong/zhaungxiubumen。运行账户、聊天、客户、许可、秘密及本机个人路径不得导出；最终全树语义隐私检查通过后才有可评审导出。推送保持远端历史，不能 force；此候选没有实际网络推送。
8. 真正生产发布、CMS 保存、部署和清理仍有各自独立门禁。周计划提案未启用；清理引用扫描不能执行 JS，坏行和无法证明的计算引用保护。学习遗失报告维持 DATA_MISSING。

恢复：before 只保存本次可采用的文件原字节与哈希。恢复需确认当前值仍等于本版应用后的 SHA，逐文件还原；并行变化先交总部，不批量覆盖、reset 或删除历史。新增文件若已有新修改亦保留，不能直接移除。
