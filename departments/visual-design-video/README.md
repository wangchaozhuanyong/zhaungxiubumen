现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# 视觉设计与视频部

2026-09-27老板新增“短视频自然增长技能学习”职责：覆盖抖音、TikTok、小红书、IG、Facebook、快手，先选真实热门/维护的GitHub Skill、学习、验证内部应用，再准确接入已验收的方法。原task_id=fc-20260927-short-video-organic-skill-study-v1，入口logs/handoffs/2026-09-27-short-video-organic-skill-study-v1.md。新来源未获准确白名单核验前只读学习；不以研究代替流量实测、不自动发布或投放。

负责 FLASH CAST 的装修视觉策略、空间展示、参考视频拆解、音乐先行短视频、文案型广告、图片、字幕动效和跨渠道视觉版本。

## 工作原则

先判断视频的信息任务，再开始创作。六类常规装修视频有简洁说明，统一中英双语、深炭灰编辑式文字；明确无字或纯空间欣赏任务才走 `visual_music/copy_mode=none`，不反向强加正文或 CTA。

需要讲知识、流程、报价逻辑或明确广告主张时，才走 `copy_led`。输入模式（自主、参考、素材或 campaign）与呈现模式分开记录。

## 固定专业 Skill

`departments/visual-design-video/SKILL.md`

它是本部门唯一入口，只路由到 4 个批准子技能：`full-house-custom-ad`、`imagegen`、`hyperframes`、`media-use`。本地参考解析和音乐目录是工具层，不扩展子技能白名单。

## 本地工具

- `scripts/renovation_knowledge.py`：活动知识唯一选择器，48场景/144深度卡、18个来源及8整屋组合；peek/simulate只读，跨类型语义去重，validate-plan检查具体动作和镜头证据，采用后commit一次并管理原风格队列。固定品牌流程不轮换。完整规则见 `references/renovation-knowledge-workflow.md`，旧主题和重复提示词退出活动目录；归档、使用账、风格辅助函数按manifest区分。
- `scripts/music_scout_preflight.py`：每日音乐采集先用 Codex `list_threads` 生成新鲜单目标快照，核验 projectId、固定任务、标题、真实目录及分组；`read_thread` 缺省项目字段不能单独当成跨项目。缺字段/错配仍阻断，不修改注册表或放宽发布授权。
- `scripts/reference_media.py`：检查环境、分析本地视频、冻结抖音参考视频、生成 ffprobe/contact sheet、可选提取音轨；默认不读浏览器，只有显式 `--cookies-from-browser` 才只读当前会话；不发布、不自动安装依赖、不保存 Cookie，并可输出无敏感信息的原因码诊断。
- `scripts/music_library.py`：列出、核验、分析和推荐音乐，生成 `music-map.json`；推荐会先按时长/视频类型/风格/情绪排序，排除最近 mounted 历史，再从最高 3 名按正权重随机。`--seed` 可复现，`--history` 只读；推荐不等于挂载、可听或授权通过。
- `scripts/validate_video_contract.py`：在调用固定模板前强制验证无文案、无自动英文、无视频内 CTA，并在 final 阶段实测音频流。
- `scripts/scene_color_qc.py`：按 storyboard 的每个 scene 中点测量亮度、高光、饱和度和暖色偏移，检查逐镜目标与相邻镜头跳变。
- `scripts/validate_cover_safe_zone.py`：验证抖音 1080×1440 的 3:4 主封面、同构的 1080×1920 首帧适配图、安全区、裁切一致性和第 0 帧证据；安全区预览不能冒充正式封面。
- 封面导演模块：`$full-house-custom-ad/references/cover-director-prompts.md`。先规划主题、人物表情动作、家具关系、图文区域与prompt，再生成；本批老板上下优先布局需在安全区报告绑定指令，不套固定皮肤。
- 文字设计模块：`references/premium-typography-system.md`；现行建筑杂志式轻注释，深炭灰中英双语，主题与细节分时。按需用 `assets/typography/light-editorial-bilingual.css`，自然留白或小面积中性浅白半透明衬底；不模糊源图、不套固定坐标，逐镜核手机可读性。
- 封面统一方法：`references/approved-cover-design.md`；深墨黑宋体中文＋清晰英文、统一标题区、局部淡石白半透明衬底和克制细框，无阴影/模糊。单独规划图文，不把正文字幕框放大，不强套竖排；旧象牙白组件仅供历史复现。
- 局部细节模块：`references/same-image-detail-lens.md`；保留同一全景，用原图同源裁切放大窗、定位框和短引导线解释柜体/抽屉，不替换成新生成近景。逐镜避让字幕和家具，按源图清晰度控制尺寸。
- `scripts/validate_douyin_publish_package.py`：验证视频描述、固定两个马来西亚话题、三个自适应话题、四类公开文字统一哈希、Qingdou 证据和封面验证结果。
- `scripts/public_copy_guard.py`：全部字幕/封面/口播/描述/话题先规划定稿，按项目风险词库筛查，生成一份完整轻抖送检文件；真实平台命中按证据去重入库，之后自动避用。只做本地汇总和证据校验，不联网代检、不伪造轻抖PASS。
- `data/knowledge/qingdou-risk-lexicon.json`：真实轻抖命中风险词/短语与证据记录；初始化未录入实测命中，不是通用法律违禁词表。
- `scripts/validate_first_frame_cover.py`：从最终 MP4 抽取第 0/1 帧及 0.50/0.70/0.90 秒证据，生成含第 0 帧的联系表，并用 SSIM 对比正式封面。
- `scripts/validate_renovation_workflow.py`：验证六个核心产物、当前批次身份、无文案路由、代表帧、逐镜色彩报告、人工审片和 final 晋级指纹。
- `assets/music/music-catalog.json`：可解码装修音频及哈希、时长、标签和既有版权状态；实时数量以 `music_library.py verify` 为准。2026-10-07老板已明确现有及以后下载入库的全库音乐均可参与本项目抖音视频制作，新曲入库后自动纳入可用池，按适配随机去重后直接挂载成片，不逐首确认；既有版权字段不改。详见音乐参考流程的全库使用决定。

完整流程见：

- `references/autonomous-renovation-workflow.md`
- `references/adaptive-renovation-workflow.md`
- `references/music-first-reference-workflow.md`
- `references/production-contract.md`
- `references/qa-gates.md`

## 输出

- 工作稿：`drafts/creative/<task_id>/`
- 候选交付：`delivery/creative/<task_id>/`
- 部门回传：`logs/department-outbox/`
- 复盘报告：`reports/`
- 学习记忆：`data/learning/departments/visual-design-video.json`
- 音乐实际使用历史：`data/learning/music-usage-history.jsonl`（仅在成片已实际挂载且有证据后追加；推荐器只读）

上传、发布、投放、购买素材、调用收费服务和客户发送仍需人工明确批准。

抖音发布硬规则：`publish/l4` 同时保留 3:4 主封面和 9:16 首帧适配图，HyperFrames 最终时间线从 0.000 秒显示后者；两者中心 3:4 构图一致。除非用户对当前批次明确要求不嵌入，否则单独提供封面不能替代视频第 0 帧。安全区预览永远只作 QA，不得进入正片。

## 任务示例

六类请求统一见 `prompts/renovation-video-request.md`；不再维护按类型分开的旧提示词。

```text
$full-house-custom-ad
做一条全屋定制方案讲解视频，用下一个轮换风格，30秒以内。
音乐从现有库适配后随机去重；按统一的中英双语文字和浅底细框封面方法制作。
按画面避让家具，需要细节时保留全景并同图局部放大。
全部公开文案整包轻抖检测，无命中直接用；交一条MP4、可点击文件夹，以及描述与5个话题合在一起，不上传或发布。
```

只要先看图，在上述请求加“先给效果图和代表帧确认，再合成”。制作请求按当前模式执行；只要求整理Skill不额外制作视频。

```text
参考这个视频做一条 15 秒 9:16 装修空间展示片。不要文案、不要英文、不要 CTA，先解析参考片和音乐结构，再做内部候选，不发布。
```

```text
做一条厨房装修避坑讲解，中英双语，先给脚本、分镜和素材需求，等我确认后再出片。
```

已正式接入的静态方法参考包：`data/learning/visual-short-video-method-reference-v1.json`，5份准确路径/hash经固定QA通过；后续短视频任务通过本部门主Skill读取。原第三方10项未授调用/安装权限，原4项制作Skill保持。
