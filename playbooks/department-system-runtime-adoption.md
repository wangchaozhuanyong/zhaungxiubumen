# 总控采用与回滚说明

本轮只制作候选，下面步骤未执行。operations在独立QA及准确采用决定后执行；不新增生产权限。所有路径归 `<PROJECT_ROOT>`，备份归项目既有 `backups/`；不用桌面临时目录。

1. 先按最终 `candidate.json` 核全部候选文件pin、实际V2/原固定聊天、来源64/59候选及当前工作流。QA或本地绿色不等于已经采用。
2. 读取当前 `tools/workflow_control.py`、`data/task-contract.json`，与 `source-baseline.json` 本轮CURRENT pin比较。若不同，基于 `exact-runtime-candidate.diff`逐段合并到新当前版本，保留根总控规则、导出工具及所有并行修改；重新冻结差异和受影响检查，回交QA。禁止用旧11文件、旧64/59候选或本目录整包覆盖当前项目。
3. 按准确许可范围备份两个运行目标及任何已存在同名新模块，记录原字节哈希/大小、是否原先存在。采用目标只有已有workflow_control/task-contract，以及新增result_coordination、qa_review_plan和只读department_next_work。policy/注册表/AGENTS/其他工具和测试夹具不在运行替换范围。
4. 先确保无正在使用旧入口的本地控制动作，再按实际采用包写准确五个目标。记录采用前后SHA与准确QA outbox/hash、候选版本、真实检查；既有CLI自动导入已采用workflow_control，不需改flashcast_ops。使用当前工作流/回执/路由测试和本候选新测试在项目内合成目录复验；核所加载模块的 `__file__` 和采用后SHA，不能把候选测试冒充运行验证。
5. 新SQLite仅在合法原结果占用或最终总部动作时生成于 `logs/result-coordination.sqlite3`，不迁移/重写历史回执。真实首次占用须核原准确queue/outbox；助理只能预检与草案，最终动作由总部。保存有限R0实际入口及占用释放/移交的真实回读，才登记运行采用验收；不据此宣布专业内容、发布或业务目标完成。

回滚条件为本次接入直接导致的原生入口/回执或并发回读失败。先停止相关控制动作，读原生准确事件和SQLite effect，收口活跃claim及uncertain（已追加则回读；未追加须明确恢复），再恢复准确备份代码/合同并验证原入口。无法确定副作用时保持具名阻断，不直接回滚后重试。保留SQLite、日志、旧原生回执及全部候选；如需数据库快照使用SQLite备份接口并在协调锁下完成，不能仅复制活跃WAL主文件或删除数据库清空占用。

新增文件回滚后可保留为未启用模块，不删除用户资料；原生历史链不重算、不重新入队、不补造收取/QA。记录恢复代码SHA、影响范围、真实检查及未完动作，由operations具名继续。跨项目、账号、Ads、Maps、CMS、网站、消息和费用边界全部沿原规则。
