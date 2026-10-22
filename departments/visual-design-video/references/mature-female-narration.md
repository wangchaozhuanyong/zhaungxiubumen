# 成熟女声装修讲解（2026-10-14老板批准）

这是原六类视频的呈现方式，不另建第七类知识库或第二套生产流程。只在明确配音任务启用；保留现行封面、双语、细节、知识去重、轻抖、HyperFrames和唯一助理验收规则。展示片默认≤30秒不变，本模式45–60秒；不上传/发布、不收费、不安装Voicebox或改共享Skill运行时。

## 已认可的制作基线

老板已选定 **A「女设计师」**，并于2026-10-14认可46.7秒衣柜示范片后要求整理规则。准确原生消息和视频指纹见 [本次认可回执](../../../drafts/creative/fc-20261014-mature-female-narration-mode-v1/rules-consolidation-v1/owner-demo-approval.json)。以后明确配音任务默认复用这套声音、较快且有语义表达的节奏和可听的低背景配乐，不重新做五声试听、不反复询问选声或逐首选曲。

- 参数唯一来源为 `assets/voice/voice-profiles.json` 的活动档案 `production_preferences`；本文件说明如何使用，其他入口和QA门不再维护第二套音量/语速默认值。声音只按老板明确新要求更换。
- 示范片只作为听感、文字层级和讲解推进的参照，不固定其衣柜选题、蓝白风格、歌曲、图数、镜头数、放大窗位置或字幕坐标。新任务继续选题去重、风格轮换和音乐适配随机去重。
- 老板认可如实记为 `OWNER_ACCEPTED_DEMO`，不倒填成未实施的完整听检、唯一助理独立PASS或父目标完成。已确认的声音和制作偏好无需因独立验收待办重复选择。

## 本地声音工具与固定版本

工具 `scripts/narration_audio.py` 是上游MLX Audio/Qwen3-TTS适配器，不是新的生产子Skill。隔离Python3.12在本项目 `runtime/qwen-tts-py312`；使用MLX Audio0.5.9。模型、缓存与依赖归项目，唯一版本来源 `assets/voice/narration-engine.json`，含准确revision、体积、许可和来源。`fetch-model`先核体积，下载后逐文件SHA冻结；运行只读冻结模型且离线，绝不自动升级、下载缺模型或转收费API。磁盘必须保留≥8GiB，空间不足只阻断依赖该资源的动作。

模型：1.7B VoiceDesign 4-bit设计声音、1.7B Base 4-bit固定复用；中文对齐用0.6B ForcedAligner 8-bit。只有代码/权重开放许可不等于生成自然感已经验收。参考[Qwen官方](https://github.com/QwenLM/Qwen3-TTS)、[MLX实现](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md)和[中文对齐](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/stt/models/qwen3_asr/README.md)。[oma-voice](https://github.com/first-fluke/oh-my-agent/blob/main/skills/oma-voice/SKILL.md)只借鉴声音档案/同文试听方法，不安装其桌面应用。

## 声音档案：首次建立或老板明确换声时

1. 首次制作五种原创成年女声：A克制女设计师、B温暖知性顾问、C低沉圆润生活讲述、D干练清楚讲解、E柔润经验分享。不得用明星/博主/未经授权录音，也不变调同一音色冒充五声。初轮同一20–25秒中文文案（包含铰链、踢脚线、柜体收口），各有纯声和配乐版，同响度、公平试听。老板明确调整节奏时沿准确新指令，不强凑旧时长，不截字或加空白；仅处理最终旁白，原始声音参考保持不变。
2. 老板在聊天明确选定编号后，才冻结原始参考音频、对应全文、设计指令、模型revision、参数、种子、音频SHA和准确选择证据到 `assets/voice/voice-profiles.json`。固定一个 `active_voice_profile_id`，不把“优先试听B”当选择，不随机换声；选择/质量未定仍标等待。正式示范片先做衣柜收纳单问题。
3. 示例经唯一未参与生产的负责助理独立验收后正式采用。首次建档检查五声差异；后续固定A的视频只核当前成片的自然感、正确读音、跨句稳定和完整审听，不要求重做五声。机器解码/时间/响度通过不能替代耳听，不自行写独立PASS或adopted。

`narration_audio.py select`仅在实际收到老板选择后使用，`--authorization-evidence`必须是本任务真实选择证据，引用reference原音SHA；不能预造决定。档案未选、哈希变更、模型失败一律明确阻断正式配音，不静默换声音/服务或降级无声片。

## 语速与表达

以活动档案引用的 `voice-expressive-v4` 女设计师试听和已认可示范片为节奏基线。老板要求比初版快1.2倍，校准是相对初版，不是每次任务再乘1.2；档案中的原声到已选试听tempo倍率只是实现该基线的起点，不是所有新稿必须机械套用的常数。新稿按实际清晰度与表达适配，已处理音轨在播放器中保持1.0倍。

按每段语义设计表达：指出痛点时有轻微提醒和反差；解释原因自然放缓；给办法时清楚、有推进感；判断和总结干净收束。重读具体动作和关键对象，停顿服务于理解，不每句同样起调、拖长元音或逐字念稿；不喊叫、甜腻、夸张演戏或靠重混响制造真人感。

音色参考始终使用未变速原音，只对最终旁白保音高校准。流程为原声拼接→已认可节奏校准→响度归一化→对最终纯声强制对齐→镜头/字幕→混音；任何后续时长变化都要重做对齐，不能沿用变速前的切点。

### 最终放行硬门（不可用口头备注替代）

- **成片45–60秒只证明时长，不证明语速合格。** 每个正式配音run都必须用 `narration_contract.py tempo-report` 将最终纯人声与活动A档案引用的已选试听，按相同口播文本口径计算语音字数/秒；比值须在 `0.90–1.10`。报告必须绑定最终纯人声与冻结口播文本的SHA。超界先改文案/声音处理，再重新对齐、重算报告；禁止把播放器设成1.2倍来补救，也禁止重复叠加最初的1.2校准。
- `tempo_calibration_path` 和 `experience_review_path` 必须作为正式合同字段，并在 `narration.evidence_sha256` 中分别固定文件SHA。任一缺失、过期、与当前run素材不符，即 `HOLD`。
- **完整体验听检必须针对最终MP4，以1.0倍速从头到尾实时播放。** 由老板或未参与制作的独立验收者填写回执，至少覆盖语速/停顿、自然表达、普通话和装修术语读音、跨句音色稳定、音乐可听度、音乐是否压住人声、口播与画面同步；不能抽听、倍速听、只看波形/响度或拿试听样片代替。
- 回执必须有唯一回执编号、带时区时间、真实执行者标识，并同时绑定最终MP4 SHA、最终纯人声SHA、混音音轨SHA、播放时长、1.0倍播放和检查项。任何一次重渲染、换音轨、换纯声或改配乐都会使旧回执失效，必须针对新指纹完整重听。结构校验只验证回执和文件是否一致，**不证明听检真的发生**；制作者不得代填自己无法证实的PASS。
- HyperFrames最终 `index.html` 必须实际挂载同一混音报告所指的混音文件；文件SHA和挂载时长须匹配。仅有混音报告、另有音频文件或MP4存在音轨，都不能证明最终渲染用了已检查的混音。
- 音乐目标差值是起混参考而非自动通过值。最终听检必须确认音乐确实听得到，同时辅音、数字、句尾与术语清楚；配乐太弱或抢声均为 `HOLD`，据实际听感调整并重做最终混音与完整复听。
- 未同时满足节奏报告、完整听检、机器合同和独立验收前，只能标 `DRAFT/HOLD`。不得交付“成片”，不得向微信群发送。

回执只使用本项目 `narration_contract.py` 校验的字段；下面是**结构示意，不是实际听检记录**：

```json
{
  "policy_version": "narration-experience-review-v1",
  "status": "PASS",
  "review_id": "当前批次唯一回执编号",
  "reviewed_at": "2026-10-19T20:00:00+08:00",
  "reviewer": {"role": "owner", "id": "真实执行者标识"},
  "playback": {"mode": "full_realtime_final_video", "speed": 1.0, "reviewed_duration_seconds": 52.0},
  "reviewed_artifacts": {
    "final_video_sha256": "当前最终MP4的真实SHA256",
    "voice_audio_sha256": "当前最终纯人声的真实SHA256",
    "mixed_audio_sha256": "当前混音音轨的真实SHA256"
  },
  "checks": {
    "voice_pace": "PASS", "voice_naturalness": "PASS", "voice_pronunciation": "PASS",
    "fixed_voice_stability": "PASS", "music_audibility": "PASS",
    "voice_music_balance": "PASS", "narration_visual_sync": "PASS"
  }
}
```

## 沿原流程，以口播驱动画面

选题事实核验 → 文案/分镜草案 → 冻结全部文字并整包轻抖 → 固定声音配音 → 实际中文强制对齐 → 语义镜头/同源细节 → 适配音乐混音 → HyperFrames → 逐镜/全片检查。

- 一条具体痛点：痛点→原因→两步改善→判断办法→简短总结。起稿约180–230汉字只作预算，实际音频45–60秒才是时长证据。按已认可的较快节奏仍超时，就精简全文、整包复检并重新配音；不额外加速塞进60秒，也不加空白凑45秒。施工/防水/电气等工程事实必须有可靠来源，不补造尺寸与保证。
- 通常8–12个有效信息段，不规定图数。先为每段写明观众要看见的对象、问题或动作，再制作对应图片/状态；一张图可推进定位、可见细节与比较，但不能整段旁白只换字幕。讲问题展示问题，讲改法展示改善，讲取用/开门/动线展示对应可见状态；改前/改后必要时保持同房间同视角。变化由语义驱动，不为了凑图重复同一空间。
- 主图稳定且满屏，仍禁持续推拉。柜体/五金讲解保留全景，同源原图局部放大；图上结构看不见就不能虚构。每段记录 `narration_line_ids`、可见证据与源图，不以不同字幕称为画面变化。
- 先实际配音再对齐，`alignment.json`保存音频/文本SHA、中文词时间；由同一时间轴派生语句、字幕、镜头切点。误差目标≤0.3秒，需实际核验，不预写已达标。强制对齐并不证明读音准确，铰链/踢脚线/柜体收口/数字必须完整审听。
- 中文旁白；屏显/封面中英对应。所有配音片按[全文同步字幕](narration-subtitles.md)烧录完整中英短句字幕，要点标题不能替代字幕，不能仅交字幕文件。字幕和镜头引用实际音频的同一时间轴，英语不遮家具、不做满屏逐字堆积。封面仍第0帧，第1帧入正文。

## 音乐和混音

配音是时间主轴，背景乐不抢节奏。按实际总长、风格/情绪从现有库适配后随机去重，优先无歌词且低干扰，连续片段必须覆盖全长，不循环凑时长。不重复追加同任务返工挂载历史；试听不是正式视频mounted记录。

纯声先两遍统一约−16LUFS。读取活动档案 `production_preferences.mix`：当前已认可的起点是音乐比人声低约12dB、轻sidechain压低（ratio1.6、threshold0.08、attack35ms、release300ms），替代旧的低20dB/强ducking方案。停顿时自然恢复，音乐应听得到但不能盖住辅音、数字、句尾和术语。

音乐片段按实际被用区间测响度，不拿未用的整曲响度替代；上述是起始值，不同歌曲按真实听感微调并记录本run参数，既不能压到几乎消失，也不能忽大忽小。调用 `mix` 时显式传入活动档案的音乐差值和压低比例，不仅依赖工具默认值。混音内部目标−16LUFS±1、真峰≤−1dBTP，不称平台官方规范。解码/响度PASS不冒充完整耳听或音乐平衡确认。

工具命令用项目内隔离解释器，所有输出显式本项目绝对路径：

```text
<项目>/departments/visual-design-video/runtime/qwen-tts-py312/bin/python -B <项目>/departments/visual-design-video/scripts/narration_audio.py doctor --output <新版本报告>
... design --request <五声请求JSON> --output <新版本结果JSON>
... select --reference-record <被选原声JSON> --authorization-evidence <真实选择JSON> --output <选择回执>
... synthesize --request <讲解语句请求JSON> --output <生成结果JSON>
... assemble --generation <生成结果JSON> --output-audio <拼接原声WAV> --output <拼接证据JSON>
按活动档案校准最终旁白节奏，记录保音高处理参数、原声/新音轨SHA；不改变原始声音参考。
... normalize --voice <节奏校准后纯声WAV> --output-audio <最终纯声WAV> --output <响度报告>
... align --audio <实际配音WAV> --text <检测版口播UTF-8> --output <alignment.json>
... timeline --alignment <alignment.json> --lines <语句请求JSON> --output <narration-timing.json>
... mix --voice <最终纯声WAV> --music <库内音轨> --music-below-voice-db <活动mix.music_below_voice_db> --ducking-ratio <活动mix.ducking_ratio> --output-audio <新WAV> --output <混音报告>
```

请求中 `publish_package_path`、`spoken_text_sha256`（原文件字节SHA）、`voice_profile_id`、`lines[{id,text,output_path}]`绑定当前整包。语句串必须精确覆盖冻结口播；禁止检测A稿却合成B稿。输出不覆盖已有文件，失败后先读回真实状态再建新run。模型和原始参考不改pitch/speed；按老板已选节奏对最终旁白保音高变速时留参数与哈希，再对该最终纯声重新对齐。

## 合同、文字和真实结果

原 `source-brief`/`video-contract`/`production-contract`保持 `presentation_mode=copy_led`、`copy_mode=narrative`，加 `timing_driver=narration`，`narration={enabled:true,language:"zh-CN",voice_profile_id:<已选>,voice_audio_path,alignment_path,spoken_copy_path,audio_mix_report_path,timing_path,tempo_calibration_path,experience_review_path,evidence_sha256:{<所有七个路径字段>:<真实文件SHA>}}`。先拼接/响度归一化，针对最终纯声做对齐，避免对齐原始声而混音引用另一哈希。storyboard沿用原scenes并增加语句ID、语义证据、实际切点，不建立平行视频合同。缺narration的旧任务不变。

final机器门核真实文件/引用/时间和听检回执中的项目：`voice_pace`、`voice_naturalness`、`voice_pronunciation`、`fixed_voice_stability`、`music_audibility`、`voice_music_balance`、`narration_visual_sync`。这些须由真实完整检查填写，不能由工具自动置PASS；producer记录不充当唯一助理独立验收。技术探针 `probe-clone`只能验证上游能生成，永不激活声音档案。

配音全文、全部中英字幕/封面、相同中英描述及两套各5话题同批冻结检测；中文固定 `#马来西亚装修公司`，英语逐项对应。只在右侧iab真实检测，无命中不再问截图确认。实见命中并保存绑定截图后由执行者自身身份记录 `AGENT_VERIFIED_REAL_QINGDOU_HIT_BATCH`，改写整包复检；只避用公开文字，内部声音指令不冒充公开内容。修改任何文案旧结果失效。没有实际检查、错版、模拟图或推测一律HOLD。

验收覆盖：首次建档或明确换声时核五声差异；每条固定声成片核成熟自然/清晰读音、跨句一致；实际45–60秒；语句-字幕-画面同步误差；不静帧到底、同源细节可见；音乐可听且不压人声；封面、双语手机可读、整包检测齐全。交付仍两份完整“相同双语描述＋中文5话题/英语5话题”，可点击视频与文件夹，不上传发布。

未完成项明确唯一负责人、下一动作和解除条件。老板未选择声音→老板选A–E；技术/制作返工→本视觉部；独立采用→注册负责助理。安装/试听不代表整片、独立验收或商业流量。
