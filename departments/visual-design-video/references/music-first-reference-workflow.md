# 音乐先行与参考视频工作流

用于少字/无字装修空间片、案例氛围片、材质展示和参考风格原创转化。

先执行 [自适应装修视频生产核心](adaptive-renovation-workflow.md) 建立当前批次和六个核心产物；本文件只负责参考正文与音乐结构，不替代代表帧、逐镜调色或 final 晋级门。

## 核心原则

1. 先判断是否需要文字，再开始创作；视觉片不靠 AI 文案填满画面。
2. 先听实际音乐，再决定时长、镜头和转场；文件名和“已推荐”都不能代替听检。
3. 参考视频必须先落地为可播放本地正文；链接、截图或口头印象不算完成分析。
4. 参考作品只提供语法和质量标杆，不提供可复制的素材、品牌、文案、音乐和完整顺序。
5. 音乐授权和技术可播放是两件事，必须分别记录。

## 本地工具

### 每日采集身份预检

先调用 Codex `list_threads`，在内存中仅提取注册表固定视觉任务的 `id/kind/hostId/projectId/title/cwd/status`。分组仅保留名称为“装修公司部门”或包含本任务的现场条目，`itemKeys` 只保留本任务，以便识别同名歧义。保存单目标快照到当天 inbox 的 `live-identity-<run_id>.json`，包含 `source_tool="list_threads"`、UTC `observed_at`、`threads` 和 `sections`；不保存其他任务、summary、聊天正文或原始列表。`read_thread` 只检查轮次和回复，缺少 `projectId` 不代表项目错配；不得用注册表补齐现场缺字段。

```bash
python3 departments/visual-design-video/scripts/music_scout_preflight.py \
  --live-snapshot departments/visual-design-video/assets/music/inbox/YYYY-MM-DD/live-identity-<run_id>.json \
  --output departments/visual-design-video/assets/music/inbox/YYYY-MM-DD/identity-preflight-<run_id>.json
```

快照有效期 5 分钟，执行前刷新。项目、固定任务、标题、真实 cwd、host、分组名称/ID 必须唯一匹配；缺失或错配返回 `BLOCKED_CROSS_PROJECT`，仅分组 ID 漂移返回 `STALE_SIDEBAR_BINDING` 并交总控恢复。此预检不修改注册表、健康记录或计划任务，也不代替消息/自动任务更新的 `policy-check`。通过后才搜索并采集；每天新增最多一条，重跑前查当天 candidate 与目录，已完成则复验并返回 `NO_CHANGE`。

### 检查环境

```bash
python3 departments/visual-design-video/scripts/reference_media.py doctor
python3 departments/visual-design-video/scripts/music_library.py verify
```

`reference_media.py` 优先复用 `<USER_HOME>/Desktop/抖音解析/.douyin-mp3-venv` 的 `yt-dlp`。可用环境也可通过 `FLASHCAST_DOUYIN_TOOL_ROOT` 指向其他位置。它不会自动安装依赖、保存 Cookie、上传或发布。

### 分析本地参考视频

```bash
python3 departments/visual-design-video/scripts/reference_media.py analyze \
  /absolute/path/reference.mp4 \
  --output-dir drafts/creative/<task_id>/reference/analysis \
  --extract-audio
```

产出 `media-analysis.json`、`contact-sheet.jpg` 和可选 `reference-audio.mp3`。这些是技术证据，不替代人工观看。

### 从抖音分享文案冻结参考

```bash
python3 departments/visual-design-video/scripts/reference_media.py fetch \
  '整段分享文案或 https://v.douyin.com/...' \
  --output-dir drafts/creative/<task_id>/reference \
  --extract-audio
```

只有视频确实需要登录且用户明确授权时，才显式增加 `--cookies-from-browser chrome`。不得复制 Cookie 文件或把登录态写入项目。只下载用户拥有、已获许可或平台条款允许用于分析的内容。

安全流程固定为：默认不读取浏览器；来源明确要求新鲜会话且负责人批准后，才显式传 `--cookies-from-browser chrome` 或 `chrome:<profile>`。适配器只允许 Chrome、Firefox、Safari 的浏览器标识，不接受 Cookie 文件或任意路径；yt-dlp 的原始输出会被捕获，不在聊天、报告或日志打印 Cookie 数量、Cookie 内容或下载签名。需要留证时使用：

```bash
python3 departments/visual-design-video/scripts/reference_media.py fetch \
  '<抖音 URL>' \
  --output-dir drafts/creative/<task_id>/runtime/reference \
  --extract-audio \
  --cookies-from-browser chrome \
  --diagnostic-output drafts/creative/<task_id>/runtime/reference-acquisition.json
```

失败诊断只保存安全原因码、参考 ID、浏览器家族、yt-dlp 版本和下一步，不保存原始下载日志或浏览器数据。`fresh_browser_session_required` 表示尚未获准使用浏览器；`browser_session_not_accepted` 表示已显式读取但来源仍拒绝；`browser_cookie_access_failed` 表示本机无法只读访问浏览器数据库。后两者应先确认正确 profile 与页面可播放，再考虑在隔离的抖音环境更新 yt-dlp，禁止导出 Cookie 文件绕过。

公开、无签名的抖音音乐 CDN 分支固定使用 IPv4、20 秒网络超时、各 1 次下载/提取器重试及 180 秒总获取上限，并忽略全局 yt-dlp 配置，避免网络等待无界或意外继承导出配置。仍按显式参数保留 Chrome 只读模式，不安装依赖、不改变登录状态。总超时仅返回 `source_network_unreachable / bounded_audio_fetch_timeout`，异常里的原始输出不得打印或落盘；确认网络与当前 profile 后进行有界重试。该修复只改变音乐 CDN 获取分支，不放宽来源、授权、单音轨、去重或发布门禁。

## 参考拆解表

人工看完视频正文与 contact sheet 后，在 `reference-analysis.md` 写：

- 视频类型：真实走拍、空间剪辑、静态图运动、工艺特写或讲解；
- 观看体验：沉浸、克制、快速种草、材质导向等；
- 首帧、首 1 秒和尾 1 秒做了什么；
- 机位起点、高度、方向和空间路径；
- 单镜时长、总切镜数、转场发生原因；
- 构图、光线、色温、材质和景深；
- 文字密度：`none`、`minimal_brand` 或 `copy_led`；
- 音乐前奏、首个清晰落点、乐句、能量段、高潮和结尾；
- 可以学习的语法；
- 必须原创的画面、音乐、品牌、文案和镜头顺序。

## 音乐库

目录：`departments/visual-design-video/assets/music/`

`music-catalog.json` 记录文件哈希、时长、来源标签和授权边界。当前迁移曲目均为历史抖音装修参考音频，默认 `authorization_status=unknown`，只可用于内部分析/草稿试听或待负责人确认的同平台候选，不能自动进入跨平台 final 或付费广告。

### 列出和推荐

```bash
python3 departments/visual-design-video/scripts/music_library.py list
python3 departments/visual-design-video/scripts/music_library.py recommend \
  --duration 20 \
  --video-type 全屋定制 \
  --style 意式极简 \
  --mood 沉稳 \
  --scope internal_reference \
  --history data/learning/music-usage-history.jsonl \
  --recent-window 3 \
  --seed 20260901 \
  --output drafts/creative/<task_id>/music-selection.json
```

推荐顺序固定为：适配度排序 → 排除最近 mounted 使用记录（默认最近 3 次）→ 只取剩余最高 3 名进入正权重随机池。`last_used` 永远不能连续复用；如果候选不足，允许放回较早的 recent 曲目，但仍排除 `last_used`。如果只剩 `last_used`，必须阻塞。未传 `--seed` 时使用系统随机源；传入整数种子后，同一目录、查询和历史会复现相同选择。JSON 输出必须保留 `selected`、`ranked_candidates`、`recently_excluded`、`top_pool`、`weights`、`seed/random_source`、`fallback` 和 `selection_rationale` 供复盘。

### mounted 使用历史

`data/learning/music-usage-history.jsonl` 是逐行 JSON、按实际挂载时间升序追加的只读推荐输入。每行至少包含：

```json
{"schema_version":"1.0","event":"mounted","mounted":true,"task_id":"fc-...","track_id":"renovation-...","used_at":"2026-09-01T09:00:21+00:00","evidence":"delivery/creative/fc-.../music-four-state.json"}
```

只有视频任务已经实际挂载音乐，且 `evidence` 指向可核验的挂载记录时，视频任务才可追加一行。`recommend` 只读取 JSON/JSONL，不创建、改写或补造使用记录。候选采集也不写这个文件。

### 每日采集与视频选曲边界

- 每日自动化每天只采集 1 条合格候选并更新音乐目录，不为具体视频选曲，不追加 mounted 历史。
- 实际视频任务必须带当前视频的时长、类型、风格、情绪、mounted 历史和 recent window 调用 `recommend`；固定种子只用于测试或需要复盘的演示。
- 推荐结果仍是 `selected=true, mounted=false`。只有挂载进工程并留下证据后，才能由视频任务追加实际使用历史；可听与授权继续分别验收。

跨平台成片检查：

```bash
python3 departments/visual-design-video/scripts/music_library.py recommend \
  --duration 15 \
  --scope external_final \
  --channel instagram
```

外部用途必须同时满足 `authorization_status=cleared`、明确 `allowed_scopes` 和匹配的 `allowed_channels`；只改成 `cleared` 仍不能放行。如果没有合格曲目，命令应返回阻塞。正确处理是补授权、使用有证据的音乐，或导出无音乐版并在目标平台内选歌。

## 运行时无文案门

在调用装修子 Skill 前运行 `scripts/validate_video_contract.py`。它会阻断：

- `visual_music` 却启用了 narrative copy；
- 自动英文或视频内 CTA；
- 固定 copy/English/CTA 模板仍为启用；
- 缺少 music selection、music map 或 visual sequence；
- final 声称有音乐但最终 MP4 没有音频流。

最小正反 fixture 位于 `assets/fixtures/`。

### 生成 `music-map.json`

```bash
python3 departments/visual-design-video/scripts/music_library.py analyze \
  --track renovation-7561383493139549491 \
  --output drafts/creative/<task_id>/music-map.json
```

脚本生成 BPM、高潮和能量段估算。必须再人工听检并补充：

- 前奏情绪；
- 首个清晰落点；
- 乐句变化；
- 与空间/材质的匹配；
- 是否有自然结尾或需要淡出。

估算不能冒充专业节拍检测结果。

## 从音乐到镜头

1. 前奏：建立入口、光线或首个空间关系；
2. 首落点：完成第一次空间揭示，不叠文案抢注意力；
3. 中段：一个镜头通常跨 4–8 拍，让空间可读；
4. 能量上升：从局部进入主空间，或从静止进入稳定运动；
5. 高潮：使用最强空间、材质或全景，不用大段 CTA；
6. 结尾：完成视线落点和声音淡出，避免突然截断。

`visual-sequence.md` 记录每段起止时间、空间、镜头运动、构图目标、对应音乐结构和真实性标签。无文案路线不创建占位字幕。

## 音轨四态

QA 必须分别记录：

- `selected`：已明确选中具体文件/平台音乐；
- `mounted`：渲染工程实际引用该音轨；
- `audible`：人工听检确认不是静音、音量过低或被错误覆盖；
- `rights_cleared`：目标渠道和用途有授权证据。

四项不能互相推导。最终 MP4 的 ffprobe 没有音频流，或人工听检不可听，均不得通过视频 QA。
