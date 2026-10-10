---
name: flashcast-cms-publishing
description: "执行 FLASH CAST 官网已有准确授权及负责助理独立验收的CMS内容保存、保护检查、回读与公开复核；不制作文案、实现代码或授予平台权限。"
---

# FLASH CAST 管理后台发布

只执行 flashcast.com.my 的既有内容字段。原专业部门冻结内容，完整目标的唯一负责助理按本版成果和对应能力独立验收并作已有授权内的常规接续；总部只读结论、确定新目标及重要授权变化。代码提交、PR、CI和部署交注册表绑定的指定开发，不在此技能中执行。

接管状态以 data/publishing/department-onboarding.json 为准。新部门建立或技能校验不等于生产权限；接管前只做内部准备。当前原任务归属、旧许可和一次性消费记录保留，新部门不得继承或重放以 content-organic-website 绑定的许可。

## 接收一个准确发布包

核原task_id、candidate_version、action、flashcast.com.my: scope、EN/ZH字段、真实CMS记录ID、冻结候选hash与来源；必须锁定 cms_content_candidate → cms_write。读取 data/task-contract.json、data/action-policy.json、playbooks/site-release-risk-boundary.md 和原workflow、当前负责助理本版验收、原授权、许可及执行回执。合法来源可以是总部原完整目标、老板准确直接任务，或已绑定负责助理/主负责人在原完整目标内落实的准确常规协作；均核现场身份、健康、scope与policy，未变版本按幂等键去重。新goal不要求QA1/QA2或总部二审，缺goal的历史任务只读其原准确链，不补新PASS。

内容已发布或执行状态不明时先回读原记录与Saved ID，不能重复保存。新goal发布前同时具备：唯一未参与制作的负责助理按准确任务/版本/哈希/能力完成的适用验收与原授权内决定、真实已有授权来源、执行者为本固定发布部的当次单次精确许可、当前before/版本防覆盖证据、受保护零写入预演、写前备份及逐字段回滚和变更日志。R0或候选自检不代独立验收，验收不授账号权限。历史AUTO_RELEASE/QA只说明原任务，不作为新goal的强制前置，也不重放旧许可。缺项只报告最小缺口、唯一保管人、恢复动作和复查时间，继续依赖齐全项；不凭技能或概括授权扩大门禁范围。

## 使用既有通道

优先使用项目现有 protected content-publish/native CMS contract，具体接口与字段从实际任务/当前能力回执读取；不虚构endpoint或参数，不从浏览器复制Cookie/Token。需要浏览器实际操作时只使用注册表批准的统一电脑控制工具 mcp__cua_repl.js（unified-computer-use），先按工具说明用一个入口调用取得真实 Chrome 标签及文档，再遵循返回文档操作老板既有已登录标签；范围/字段、执行者及预演或写入仍受准确验收、原授权和精确policy限定。不能使用新的无登录浏览器替代，不能读Cookie/Token/凭证或扩大字段；接口未提供或登录态缺失时报告准确阻断。工具层参考 tools/native_cms_admission_v2.py、tools/managed_cms_permit_issuer.py 和任务绑定输入；控制许可沿既有issuer与精确负责助理准入路径签发，发布部不自行改issuer/注册表/权限。

预演或防覆盖检查未上线时，不用普通Save绕过。合法会话401/OTP/缺角色时单次回读后交实际保管人；不反复尝试、不索要密码。写入只用冻结字段/值，保留其他内容，不擅自补文案、价格、真实案例、审核署名或服务范围。一次提交后记录真实Saved ID/版本；超时先回读，不重放消费许可。

## 收口

CMS已保存、公开可見、原始HTML与渲染正文按任务要求核对，分别记录；公开复核失败按原准确回滚方案由有权执行者处理，不扩大回滚范围。没有公开证明则保持未完成，排名/自然流量/AI效果另行统计。

每轮完成、部分完成、失败、助理返工、外部阻断都先在固定聊天非空汇报，再冻结报告/经校验V2 outbox；沿原task/candidate/result hash登记notification_queued，专业结果只交唯一负责助理。主负责人按完整目标声明的授权范围收回子结果及落实必要协作，不逐段回总部审批；本技能不赋予越界派工权。普通通知遇active聊天精确暂缓，实际空闲/完成后经政策检查送达一次并留原生回执，入队不算送达。给出实际保存/未保存、已验/未验范围、唯一下一负责人、所需输入、恢复动作、解除条件和复查时间；队列、文件或closed不是业务完成。
