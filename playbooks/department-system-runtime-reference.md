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

## CMS pre-main consumed-instance recovery

原已消费policy后的真实issuer import失败，只能用`python3 tools/professional_cms_pre_main_recovery.py draft --failure-report <真实完整PUB报告> --issuer-source <准确旧issuer源码> --output <新不可变来源>`和`record --input <该准确来源>`登记事实边；它不签发/重置/重消费policy，不创建permit或调用HTTP。入口核原授权/请求/实际policy、原PUB完整failed原生输出、observer/旧issuer代码的main前边界，以及零permit/run和全行未变；主函数/UUID/HTTP阶段及未知效果不适用。闭合目标不能新增执行实例。

原PUB用`status --task-id <原task>`读取真实event/source和fresh-effects结构。原键SELECT、全行/微秒CAS、run列表和自身真实读回命令须新鲜；历史dryrun或零行不是未来freshness。先把execution_instance（event/source/fresh_effects）加入新请求，再生成intent与四证，沿正常preflight/自身readiness/新policy一次执行。旧spent行与原失败保持，作为已核真前驱，不能直接重放或当新请求许可；同一新实例不重复消费。最终UUID/HTTP前重新核对实例与源。逆向仍走自身真实completed父permit/run和当前postSave CAS的独立新许可，不沿用forward恢复实例。

## R3 normal binding transport

已登记的外部WEB完整发布源使用`python3 tools/r3_platform_binding_transport.py describe --task-id <原task>`读取现行入口。原WEB先在原worktree用`inspect --task-id <原task> --run-id <真实既有pending run>`核同账号、实际main/run/attempt1和原环境保护；这只是只读运输前提，未探测写权限、未签发或审核环境。即时可执行后才沿原fresh preflight/approval-record真实签发短期引用，再用`install --task-id <原task> --approval-id <真实已签发引用>`承运并读回；`status`只核原键。SYS不代操作平台；不得以预期apr、fixture或旧source构造真实绑定。

入口只追加一个原真实issuer绑定，保留有效既有条目和原变量层级，不改guard/reviewer/保护，不发起或重派run、不审核环境、不自动消费本地许可。写意图先持久化，未知效果只能读回，不清attempt或盲重发。过期、冲突、容量满、其他旧条目不符合原guard时准确阻断该运输，不擅删其他issuer条目。

GitHub变量API不支持条件写CAS；本地按同仓库变量串行锁、两次原生值/时间戳比较及完整写后读回，不将本地SHA称服务端CAS。原WEB是唯一正常承运执行者；并发远端编辑无法被本地锁原子隔离，需保留此限制并在冲突/未知时停止该写，不覆盖或回滚他人更新。平台403等仅记录脱敏HTTP类别及原键，不输出Token或请求凭证，不自动扩权限。自然登录、其他任务及共享socket不是本入口前置。

## recovery

先核已发生效果和原幂等键；中断不伪造completed。保留原当前/暂停位置，普通恢复不换生产者。

店铺原实例已消费策略后在本地签发前过期时，现有有界入口为`python3 tools/shop_office_six_field_execution.py preissue-recovery-draft --input <真实完整失败报告>`及`preissue-recovery-record --input <准确不可变恢复源>`。入口核原请求/消费策略、真实PUB完整原生失败和原键效果，仅追加恢复来源，不签发permit或保存CMS。原PUB仍须临近执行重新取得真实查效、完整行/CAS及保护预演，先绑定新实例再构造intent四证，并使用独立的新正常policy；旧策略不重用，300秒查效和最终执行门禁保持。

## finish

dispatch-plan --goal；receipt-record实际派送/ACK；`python3 tools/goal_delivery_runtime.py completion-evidence-record`登记真实证明；`python3 tools/goal_delivery_runtime.py status --task-id <原task>`读回。新自主合同证明schema为department-autonomous-actual-effect/v1。旧开放的内部交付合同若仅含accepted_delivery标准，原专业owner可沿同一completion-evidence-record逐项登记原完整成果、自检、真实固定聊天来源、协作result_received和HQ已提交SQL/native知悉证明；保持原标准与历史QA，不要求退役助理重新验收。此兼容不含生产、typed采用或公开父目标关闭，status只读回准确本地完成范围。

## daily

既有专业排程保持；HQ兜底时刻只读唯一现行正文和真实自动化注册表，本页不复制排程。无变化静默，不新建轮询。

## maintenance

仅准确授权的本项目专业维护。原flash-cast-20-00的当前状态、专业执行绑定和检查范围沿maintenance-preflight实时读取；激活、真实排程运行与清理效果分别记实，历史A3许可不继承，预检不执行删除。

## target-state

忙窗口不插话，notLoaded不把accepted当启动；由原HQ第一方读取状态后一次合法恢复。

## notice-recovery

先读运输及实收；未知效果不盲重发，单事件异常隔离。

后台重启核验使用`department_event_dispatcher.py login-status/background-status`，只认当前安装的`com.flashcast.department-event-dispatcher`、真实用户domain、单PID/锁、service-ready和完整scan中的源码读回。实际OS/登录周期另以真实boot、launchd启动时间和同PID的ready/scan证据记录；只读status中的固定测试标记不代替该周期证据。不为核验再次重启、另建daemon或重放运输。官方共享桌面控制端点与已可工作的官方入队是两项能力：端点缺失仍须具名，不以历史读取或第一方人工恢复冒作无人值守完成。

专业CMS issuer的当前可执行target目录排除真实已关闭/取消/失败目标；原注册来源和回执历史仍保留。目录排除不放宽新签发、逆向、角色、字段或单次许可校验；活跃目标的缺失或错误来源继续严格拒绝。测试按当前自主路由断言，历史助理夹具只验证历史分支，完整外协夹具须在冻结时包含原owner/授权/声明及实际host/kind来源。

## authority-change

真实老板新授权改变模式，原合同/业务权限不扩大。


维护接线读回：`python3 tools/department_autonomy.py maintenance-preflight`。原flash-cast-20-00由SYS承接本项目检查，平台状态和绑定以准确实际读回为准；该命令不清理文件、不继承A3许可。实际清理仍须准确使用/引用、任务结束事实、精确清单和当前授权，不可恢复范围另向老板确认。

### 已消费实例的artifact身份拒绝接续

`professional_cms_pre_main_recovery.py draft-artifact` 仅消费真实 main 内 artifact 身份拒绝、UUID/CMS issue 前的失败源；与旧 pre-main import 事实分别登记。保存失败时 issuer 字节，绑定原请求、预检、spent policy、前一实例与当时真实新鲜查效、原生失败命令及其后零效果。`record` 只追加来源，不回写旧策略；`status --task-id` 返回准确当前源事件和完整 spent lineage。源必须形成唯一顺序后继，未知/非零效果或新分叉拒绝。原PUB使用当前源事件和新鲜查效重绑准确请求，沿原 preflight/readiness/新单次 policy/issuer 执行；300秒、预演期限、完整行/CAS和原单次约束不变。

professional 动态 `target | dry-run` 名称仅沿真实登记目标和 active 原 workflow 身份消费，repo/id/path/ref/head/attempt、actor/OIDC、制品、字段/备份/父许可校验继续执行。历史 run 只作原失败和连通验证证据，过期不得当当前生产就绪。SYS不代PUB签发或保存。

### 已采用WEB元数据增量的正常版本接续

`professional_web_increment.py record --task-id <原任务> --input <准确来源登记>` 验证原专业owner实际采用、原WEB真实运输/ACK/completed结果、Git对象及精确前后patch，仅追加来源，不改原合同、producer和旧生产上下文。注册来源须绑定原`professional_WEB_production_source`。metadata expected值只能沿原严格完整标题及实际源核对改变，CMS tuple、publisher实现和其他字段保持；真实新branch/worktree/native随已验来源选择，不由caller覆盖旧ctx。

原`professional_web_execution.py request-base/build-preflight`保持入口；已登记元数据增量仅支持准确新head的push/PR/所需官方CI/merge，未生成的PR/main/run不预填，不重放CMS/preview/issuer/R3/Edge或手动Pages。WEB先鲜读状态，再由自己的真实原生自检绑定当前intent与原授权SHA；SYS不代签。源代码15项等未变证据按相同字节复用。实际merge自然触发的正常流程分别记实。

同一原WEB已登记版本的CI触发路径后继沿同一`record`入口追加`professional-external-WEB-CI-path-successor/v1`，绑定原来源和已登记parent来源、原owner真实决定及WEB正常运输/completed结果。仅允许向原PR的`on.pull_request.paths`加入已采用源路径，去掉新增行后整个workflow必须与parent逐字节一致；旧target/test、jobs、Node22、permissions及严格检查保持。真实Git parent与累计integration base分别验证：state以`candidate_parent`提供前者，`candidate_base`及真实remote main提供后者，不能互相冒充。原branch、worktree、actor和既有PR身份保持；状态中的`pull_request`须有真实number/base_branch/head_branch/head_sha。push仅在原branch仍为parent或该准确head时接续；PR入口只读同一个已存在PR，不另造PR。所有必要官方CI须来自新head，旧head绿灯不得复用；没有当前WEB自检/备份/正常单次policy仍不能执行。

## 专业逐对象执行源与声明日任务成果

广告逐对象来源使用既有`goal_delivery_runtime.py approved-action-record`的`professional-ads-object-source-registration/v1`，准确关联原合同、原人类/协调源、已完成专业请求与有界逻辑对象；登记不签发许可。`professional-ads-object-preflight/v1`沿原`preflight-record`进入当次真实观察、自检和可见备份，再走正常`policy-check`与执行前一次占用。`professional_ads_execution.py source-check/status/reserve`只读本地来源或登记一次占用，不访问广告平台；v1入口仅支持其已准确计划的单个新广告组，不能借给其他对象。原观察不改时，执行前才鲜读同一授权通道和实际支持字段；临时浏览器编号不作稳定身份，未提供的服务端CAS或新对象ID不编造。

已在`task-contract.result_handoff_contract.scheduled_daily_sources`声明自主模式/专业来源/日期模式及`result_receiver=operations`的日任务，沿原V2/真实固定聊天READY或已完成final及正常结果交接入口运输和实收，不创建人工goal、派工ACK或助理批准。实收仍须准确原结果身份、完整证据SHA、真实HQ读取及SQL/native一致；声明日任务不产生业务发布或账户权限。已有goal或goal_contract的损坏快照不能冒作无goal日任务，历史旧模式继续原来源读取。

同一原计划的后续对象沿`professional-ads-plan-object-source-registration/v2`只登记一次真实原计划、原建组实际结果、原图及老板新增预算原生来源；旧合同/原预算和group-only许可原件不改。新预算只约束同系列共享日均及原期限，授权值与实际Saved值分别读取。正常`approved-action-record`只追加source；不签发、不消费账户许可。

`professional_ads_execution.py derive --input <已登记来源> --key <原plan key> --kind group|upload|ad|budget --output <新请求>`从原计划派生准确窄动作。原已建组不再派生，重复图按原SHA共用上传效果，其他真实group/asset/ad ID由执行者原生读回，不能编造。每动作分别采集本次支持的完整原对象表/稳定profile与extension/实际临时handle/真实日均预算和当前表单，自检绑定同一intent_sha256。`freeze-preflight --input <derived_request/facts/self_check三个准确pin> --output <新目录>`仅冻结可见备份/无重放恢复和`professional-ads-planned-object-preflight/v2`；`preflight`登记后正常`policy-check`，仅原执行者临近外部效果调用`issue`并`reserve --input <该窄请求> --decision-id <本次新policy>`一次。

上传、建广告、预算保存是三个独立效果；广告仅消费已登记真实upload effect/crop/assetID与原图SHA。`effect-record --input <真实原生观察证明>`验证原执行者的第一方实际UI调用、原policy/reservation、即时对象表与支持字段后只追加效果。未知先读原键，不重复外部写；`derive`的existing_issued_policy_ids不为空时不得换新请求重试。同预算已实际Saved为新值时只读回，不再Save。报告/制作来源不因秒级观察过期而重做；只有真正执行事实须临近鲜读，未暴露服务端CAS/ID如实未提供。上传/建广告在实际合法旧值或新值下可独立执行，不等待预算保存；不得据此扩账号、地域、期限、其他预算或条款。

## 原本地阶段之后的代码发布来源

真实老板后继授权与HQ准确范围不回写旧local-only合同；原专业owner和producer保持，外部WEB仍是声明执行者。`professional-external-WEB-owner-followon-source/v2`沿现有`goal_delivery_runtime.py approved-action-record`登记：须原冻结goal、真实human、已送达原WEB并真实completed的准确候选/拒绝来源、原Git对象/所有路径与正逆patch。只追加来源，不重开本地闭合或签发网站许可。

正常`professional_web_execution.py describe/request-base/build-preflight`复用；原WEB临近执行鲜读actor/repo/main/branch/PR/同head官方Node22 CI和未知效果，自身实际原生facts/selfcheck及源备份后沿正常preflight/policy单次办理。代码来源仅支持准确push/PR/CI/merge及必要既有Pages，不取得CMS/R3/Edge/DB/auth/账号/费用权限。已有同head成功自动Pages只读回，不重复手动dispatch。

真实main前进后由原WEB形成同语义patch的必要后继；来源消费者验证原base祖先、准确原路径和语义，禁止用新head夹带业务变化或force旧base。`source-backup --task-id <原task> --state <真实当前state> --output <本项目内新目录>`只冻结当前真实Git正逆patch和source backup，供原build-preflight；不造未来PR/main/run，也不是远端备份或平台回滚效果。已发布后逆向须`state.code_recovery_source`绑定原实际allow policy、原WEB成功原生读回的own_candidate/current_main/完整SHA与时间，才可沿新逆向commit/PR/CI及新窄policy执行，不借别的任务许可或恢复整旧树。
