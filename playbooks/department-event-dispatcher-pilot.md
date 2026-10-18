# 部门交付后台事件接续

本程序只运输原成果通知，不制作、验收、授权或发布。现行职责和完成标准按唯一共同规则；准确运行范围由 `data/department-event-dispatcher.json` 决定。

## 已实际接通

2026-10-16已验证应用自带官方 `codex queue --thread <原聊天> --message <准确正文>`：只读消息启动原助理3并返回原成果SHA；后台接续程序随后实际投递原助理2、3，两份原成果均已通过原入口收取。旧命令行没有queue命令，运行时使用配置中的应用自带版本。

官方队列处理忙碌接收者，后台不调用steer或普通直接发送。独立app-server仅查询持久化身份和历史，不能据其notLoaded判断忙闲，也不能用它resume/start轮次。共享proxy直连模式仍须真实ACTIVE哨兵验证；缺socket的旧观察只限制该直连模式，不阻断官方队列。

## 当前准入和去重

- 复用原 `logs/result-notifications`、任务ID、候选版本、哈希及唯一助理；不另建审批账。
- 指定两份旧成果恢复；激活时间后的新结果须有真实原入队事件和原来源映射。完整目标和合同已准入的日检分别使用自身真实来源；不能给日检伪造完整目标或总部派工，不会重放全量历史。
- 实际prepare-message入口将结果通知交给原发送者的notification_claim与准确department_result政策。助理向总部知会不是新增部门派工，也不要求整个业务目标已经关闭；其他旧来源或映射不全继续保留准确原因和每日兜底。
- SQLite仅保留运输意图、官方消息ID、实际轮次和不确定状态。队列接受不写成notification_sent、controller_received、QA或发布。
- 原通知记录保存运输占用；发送部门不能在后台已占用时重复发送。接受后尚无实际收取的结果仍是待办；超过接续宽限后，恢复入口核真实原生状态及效果，只恢复既有队列，不盲重发业务包。单个无效来源隔离，不堵其他结果。
- 先提交意图再投递；超时/中断先核原始精确正文效果，不盲重发。接收者实际收取后沿原业务记录去重。

## 当前会话后台进程

项目后台使用macOS kqueue阻塞等待结果通知、实际收取JSONL及相关配置变更，不定时扫描聊天，不占用总部模型守候。进程日志和PID均在本项目 `logs/department-event-dispatcher`。

- `python3 tools/department_event_dispatcher.py start-background`：从已有项目访问权的应用启动事件进程；已有进程则不重复启动。
- `python3 tools/department_event_dispatcher.py background-status`：核本项目准确PID和实际命令。
- `python3 tools/department_event_dispatcher.py stop-background`：只停止已核实的本项目进程。
- `python3 tools/department_event_dispatcher.py status`：查看运输状态。
- `python3 tools/department_event_dispatcher.py queue-once`：处理一次准入结果；正常常驻时由独占锁阻止另一个写入者。
- `python3 tools/department_event_dispatcher.py stage-once`：零发送保留原待办。

独立launchd试验被系统拒绝读取桌面目录，失败启动项已撤销，没有修改系统安全设置。当前进程已验证在启动命令结束后继续运行，但尚未启用重启/重新登录自启动；不能承诺应用关闭或电脑重启后仍即时接续。断开时保留原运输状态，沿本入口或每日兜底恢复。

## 验证边界

真实原聊天的接收、验收、下一动作和发布分别留证。忙时排队已实测原轮正常结束后另起轮次，未打断；未加载聊天仍有队列接受却未启动的实测反例，不能承诺所有此类通知自动开始。恢复一次原生通知已实际启动原助理2，运输接受和实际收取仍分别记录。网站实际保存、部署和公开复核仍由对应原任务负责，不能因本程序接通就宣称网站已发布。
