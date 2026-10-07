# FLASH CAST 部门协作系统

现行规则是 [部门系统现行规则](playbooks/department-system-current.md)。当前11个固定角色：总部、总部助理、网站增长、SEO/GEO研究、本地/地图、数据/付费研究、视觉、销售、质检1部、质检2部、后台发布部。

本目录是部门协调与证据系统，不是官网源码或广告账户。专业部门制作准确候选，独立质检审核，总部决策，指定执行者按合法通道实施；后台发布与网站代码发布分开。任务结束不等于业务目标达成。

## 日常工作

1. 总部核当前原任务、真实身份、健康和路由，向最少必要固定部门派一次有界任务。
2. 部门先接单，在自己的固定聊天报告实绩/未完/问题/专业新增机会，冻结V2回执，唯一入队并回读。
3. 助理预核准确结果和证据、提交下一动作草案；总部保留最终决策。普通结果不插话打断在途工作。
4. 总部记录收取、决策，并关联真实下一派工/执行/公开复核，或具名外部等待及复查时间。
5. 部门按既有任务包明确授权的独立R0步骤继续；每天研究检查专业漏项。停止前总结未完成范围和下一负责人。

常用只读检查：

```bash
python3 tools/flashcast_ops.py result-handoff-pending
python3 tools/flashcast_ops.py department-learning-status
python3 tools/flashcast_ops.py workflow-status --task-id <原任务ID>
python3 tools/qa_dispatch_priority.py
python3 tools/controller_event_state.py
```

`pending_count=0`不等于收工，还要核followthrough、真实在途任务和业务主账。每日15:00汇总、18:00兜底补漏；不新增五分钟轮询。队列本身不会自动唤醒已经结束的聊天，本轮原生完成事件等待和后续自然接续负责衔接。

2026.10.07 接续补丁从政策最新检查点和真实回执生成准确等待列表，替代手工旧缓存；已收取、决策并落实的范围不再被旧watch反复追踪。项目停止检查配置在 `.codex/hooks.json`：需在 Codex `/hooks` 审阅并信任后才运行，公开源码不会导出本机信任或自动启用。它只防本轮普通结束漏收，不能唤醒已结束聊天或恢复人工中断。详见[结束前核验](playbooks/controller-result-continuation-and-checkout.md)。

## 规则与岗位入口

- [项目规则](AGENTS.md)。本机运行配置为data/task-contract.json、data/action-policy.json和data/department-registry.json；公开仓库提供[机器合同模板](examples/task-contract.example.json)、[动作政策模板](examples/action-policy.example.json)及[注册表模板](examples/department-registry.example.json)。
- [总部](departments/operations/SKILL.md)、[助理](departments/operations-assistant/SKILL.md)、[质检1](departments/qa/SKILL.md)、[质检2](departments/qa-technical/SKILL.md)、[发布部](departments/publishing/SKILL.md)。其余岗位在departments中。
- [专业每日循环](playbooks/department-daily-professional-loop.md)、[停止前核验](playbooks/controller-result-continuation-and-checkout.md)、[结果恢复](playbooks/result-notification-key-and-recovery.md)。

质检2部只在机器合同精确准入范围内记录正式审核；旧工作流默认保留质检1部。QA的内部通过不自动赋予账号或生产写入权限。助理不签发最终决策或生产许可。

运行协调入口采用项目内SQLite占用和原生结果回执，关联原任务、部门、候选版本及最终outbox哈希。占用最长15分钟；中断先回读已发生的动作，再显式恢复。身份字符串只用于审计，不能充当账号认证或全局工具拦截器。准确QA2准入只覆盖R0内部/只读候选，生产审核仍沿原质检1链。

入口说明见[运行采用与恢复](playbooks/department-system-runtime-adoption.md)、[结果协调](playbooks/department-result-coordination.md)和[质检2精确准入](playbooks/qa2-exact-r0-admission.md)。这些入口不会替用户创建聊天、发送消息、部署或签发生产许可。

## 从公开源码安装

依赖Python 3.9以上及标准库；Codex聊天与工具权限仍需由用户实际配置。克隆后执行：

```bash
python3 tools/setup_department_system.py
python3 tools/flashcast_ops.py department-status
```

初始化只创建本地空模板，重复执行不覆盖数据；所有聊天默认unbound、不可派工。填写七份公司确认资料，根据Codex现场逐一绑定真实项目/聊天/标题/cwd/分组及有效非空回复，再通过精确健康和路由检查。不得复制他人的聊天ID、账号、数据、历史批准或消费记录。专业子Skill只按岗位白名单在本机提供，公开包不会代装第三方技能或连接账号。

## 安全与结果边界

Google Ads保持HOLD/OFF/RM0；不自动联系客户，不处理付款、价格承诺、账号权限、密钥、DNS或硬删除。网站/地图写入需各自准确候选、独立QA、有效授权、精确单次许可、真实执行与公众复核。

50个自然来源去重IP/日按合法口径核验，缺数据是DATA_MISSING，AI效果未测是NOT_MEASURED。候选、QA、Saved、部署、公众验证与增长分别记录。

## 发布本系统源码

持续检查配置位于ci/department-system-checks.yml.example，包含Python 3.9、3.12两组控制检查。本次GitHub登录没有创建Actions工作流所需的workflow权限，因此模板尚未放入.github/workflows，GitHub自动CI未启用。管理员以后用具有相应权限的合法登录配置；本包不更改登录或账号权限。本地可在tools目录运行模板列出的unittest命令。

只用allowlist导出工具，不把整个运营目录直接上传：

```bash
python3 tools/export_department_system.py --target <项目内发布目录>
```

公开包包含岗位规则、工具源码和脱敏配置模板；不含本机聊天/健康证明、客户线索、账号资料、原始结果账本、CMS权限或历史生产许可。release-manifest.json记录源码与导出字节指纹。GitHub推送另按用户对准确仓库的授权执行。

2026.10.07.4 包含已独立验收的精确发布执行者移交和后继 QA 控制方法源码。公开模板清除本机候选准入绑定；这些项目专用方法依赖原项目的真实来源与回执，缺少时拒绝执行，不是可直接启用的发布服务。正式分发检查使用上面的 CI 模板测试集；发布许可工具另在具备合法原项目输入的本机环境验收，不把缺失私有输入时的导入拒绝当作账号或生产许可。
