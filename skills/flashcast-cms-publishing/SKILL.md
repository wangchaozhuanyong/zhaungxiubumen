---
name: flashcast-cms-publishing
description: "执行 FLASH CAST 官网已通过准确独立QA的管理后台内容发布、写前保护检查、保存回读与公开复核；不修改文案、网站代码或平台权限。"
---

现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# FLASH CAST 管理后台发布

只执行 flashcast.com.my 的既有内容字段。总控负责派工和审核，内容由原专业部门冻结，独立固定QA验收；代码提交、PR、CI和部署交老板指定的装修网站开发，不在此技能中执行。

接管状态以 data/publishing/department-onboarding.json 为准。新部门建立或技能校验不等于生产权限；接管前只做内部准备。当前原任务归属、旧许可和一次性消费记录保留，新部门不得继承或重放以 content-organic-website 绑定的许可。

## 接收一个准确发布包

核原task_id、candidate_version、action、flashcast.com.my: scope、EN/ZH字段、真实CMS记录ID、冻结候选hash与来源；必须锁定 cms_content_candidate → cms_write。读取 data/task-contract.json、data/action-policy.json、playbooks/site-release-risk-boundary.md 和该任务原workflow/QA/许可/执行回执。只接总控经过现场身份、健康和policy放行的原任务；未变版本按幂等键去重。

内容已发布或执行状态不明时先回读原记录与Saved ID，不能重复保存。发布前同时具备：候选精确生产级QA PASS（R0审阅不够）、总控AUTO_RELEASE、执行者为本固定发布部的当次单次精确许可、当前before/版本防覆盖证据、受保护零写入预演、写前备份及逐字段回滚和变更日志。缺项就报告最小缺口和保管人，继续其他依赖齐全项，不能凭技能或老板概括授权绕过门禁。

## 使用既有通道

优先使用项目现有 protected content-publish/native CMS contract，具体接口与字段从实际任务/当前能力回执读取；不虚构endpoint或参数，不从浏览器复制Cookie/Token。需要浏览器实际操作时只使用注册表批准的统一电脑控制工具 mcp__cua_repl.js（unified-computer-use），先按工具说明用一个入口调用取得真实 Chrome 标签及文档，再遵循返回文档操作老板既有已登录标签；只读范围/字段、执行者及预演或写入仍由独立QA和精确policy限定。不能使用新的无登录浏览器替代，不能读Cookie/Token/凭证或扩大字段；接口未提供或登录态缺失时报告准确阻断。工具层参考 tools/native_cms_admission_v2.py、tools/managed_cms_permit_issuer.py 和任务绑定输入，由总控签发控制许可，发布部不自行改issuer/注册表/权限。

预演或防覆盖检查未上线时，不用普通Save绕过。合法会话401/OTP/缺角色时单次回读后交实际保管人；不反复尝试、不索要密码。写入只用冻结字段/值，保留其他内容，不擅自补文案、价格、真实案例、审核署名或服务范围。一次提交后记录真实Saved ID/版本；超时先回读，不重放消费许可。

## 收口

CMS已保存、公开可見、原始HTML与渲染正文按任务要求核对，分别记录；公开复核失败按原准确回滚方案由有权执行者处理，不扩大回滚范围。没有公开证明则保持未完成，排名/自然流量/AI效果另行统计。

每轮完成、部分完成、失败、QA返工、外部阻断都先在固定聊天非空汇报，再冻结报告/经校验V2 outbox；沿原task/candidate/result hash登记notification_queued。不向总控聊天插话，不自行派下游。给出实际保存/未保存、已验/未验范围、唯一下一负责人和解除条件；队列、文件或closed不是业务完成。
