# 部门系统运行接口参考

共同行为只按[唯一现行正文](department-system-current.md)，本页只列现有接口。

## messages

正常prepare-message沿原task/scope、真实固定身份、原授权及完整payload；专业部门直报operations和协作回原owner。完整当前目标的专业owner回operations知悉；明确协作回原owner，历史parent的当前owner不自动替换本目标接收者，已有队列目标保持冻结。

声明外协的官方队列：`python3 tools/goal_source_recovery.py prepare-message --input <真实当前request>`；仅`delivery_mode=official_native_queue`且正常返回`ready_to_queue`后，原发送方用`python3 -B tools/goal_source_recovery.py queue-collaboration --request <request> --prepared <prepared> --directory <本项目原唯一logs/handoffs目录>`。真实active窗口可排队；普通直接send仍须idle，unknown不能填idle。

运输回执沿原`goal_delivery_runtime.py collaboration-record`：`source_kind=official_native_queue`分别记录`queue_accepted`、真实原生正文/非空ACK齐全的`message_received`、真实completed完整结果的`result_received`。先持久化原task/action意图；断线/未知效果读原目录，不换目录重发。接受不证明窗口启动或实收，实收不证明业务完成。

## delivery

正常完整outbox/READY与官方result queue；notification_queued仅运输待办，controller_received要求真实接收原生及SQL/native一致。

闭目标的完整最终结果仍由原owner使用原冻结输入执行`python3 tools/flashcast_ops.py result-handoff-record --input <同一final request>`。先读原identity/幂等键的实际效果；已有记录不重收，未写才唯一登记。此路径须真实原生READY、原完整scope/成果SHA和全部正常完成证明，只有HQ知悉归档，不恢复业务执行或签发许可。

已登记只读协作的原专业接收者归回原owner，可在原prepare-message输入附readonly_result_return的真实原动作、正常prepare/policy、原官方队列/成功命令、原生实收/非空ACK/完成结果及准确源pin。此分支不增加业务producer或写许可。原owner的真实原生消息已逐SHA读到同一结果时，返回already_read_by_original_owner，保留旧拒绝且不重复运输或代写正式实收；否则仍须正常唯一发送与效果读回。

## acceptance

普通目标由专业owner自检与实际效果读回，无助理QA。历史qa_verdict仅按原冻结来源读取。

## production

原有权执行者即时鲜读、准确任务请求、自检、版本/CAS、备份/回滚、幂等和真实结果。敏感新增事项单独报HQ。

冻结自主合同原执行动作为空、原专业owner已在真实完整成果中选定准确CMS差异时，用既有approved-action-record登记schema=professional-cms-execution-source-registration/v1。入口核原criterion/人类授权、原owner真实completed命令与READY、SQL/native已提交知悉、完整before/desired/carrier及准确PUB/WEB身份，仅追加professional_cms_execution_source事件，不修改冻结producer/动作/只读记录，不签发许可。读回：python3 tools/professional_cms_execution.py status --task-id <原task>。

源内新增PUB/WEB协作消息仍由原owner正常approved-action-record及prepare-message办理；消息必须带professional_execution_source注册pin、原execution_tuple和准确payload，保留业务scope，物理CMS scope另映射。原PUB实际收到该精确协作后，fresh preflight使用schema=professional-cms-fresh-preflight/v1（request为完整当前请求pin）沿既有preflight-record进入；全行/CAS、真实查效、零写预演、自检/备份和自身新单次许可仍须满足。源登记不是远端target/CLI/runtime已加载，也不代替实际Save。

## recovery

先核已发生效果和原幂等键；中断不伪造completed。保留原当前/暂停位置，普通恢复不换生产者。

店铺原实例已消费策略后在本地签发前过期时，现有有界入口为`python3 tools/shop_office_six_field_execution.py preissue-recovery-draft --input <真实完整失败报告>`及`preissue-recovery-record --input <准确不可变恢复源>`。入口核原请求/消费策略、真实PUB完整原生失败和原键效果，仅追加恢复来源，不签发permit或保存CMS。原PUB仍须临近执行重新取得真实查效、完整行/CAS及保护预演，先绑定新实例再构造intent四证，并使用独立的新正常policy；旧策略不重用，300秒查效和最终执行门禁保持。

## finish

dispatch-plan --goal；receipt-record实际派送/ACK；`python3 tools/goal_delivery_runtime.py completion-evidence-record`登记真实证明；`python3 tools/goal_delivery_runtime.py status --task-id <原task>`读回。新自主合同证明schema为department-autonomous-actual-effect/v1。旧开放的内部交付合同若仅含accepted_delivery标准，原专业owner可沿同一completion-evidence-record逐项登记原完整成果、自检、真实固定聊天来源、协作result_received和HQ已提交SQL/native知悉证明；保持原标准与历史QA，不要求退役助理重新验收。此兼容不含生产、typed采用或公开父目标关闭，status只读回准确本地完成范围。

## daily

既有专业排程及HQ18:00兜底保持；无变化静默，不新建轮询。

## maintenance

仅准确授权的本项目专业维护。原flash-cast-20-00的当前状态、专业执行绑定和检查范围沿maintenance-preflight实时读取；激活、真实排程运行与清理效果分别记实，历史A3许可不继承，预检不执行删除。

## target-state

忙窗口不插话，notLoaded不把accepted当启动；由原HQ第一方读取状态后一次合法恢复。

## notice-recovery

先读运输及实收；未知效果不盲重发，单事件异常隔离。

## authority-change

真实老板新授权改变模式，原合同/业务权限不扩大。


维护接线读回：`python3 tools/department_autonomy.py maintenance-preflight`。原flash-cast-20-00由SYS承接本项目检查，平台状态和绑定以准确实际读回为准；该命令不清理文件、不继承A3许可。实际清理仍须准确使用/引用、任务结束事实、精确清单和当前授权，不可恢复范围另向老板确认。
