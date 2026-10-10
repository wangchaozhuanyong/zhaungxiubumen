---
name: flashcast-visual-design-video
description: "FLASH CAST 装修视觉与视频专业 Skill。规划、制作、返工和质检六类装修短视频、效果图与封面；统一中英双语编辑式排版、音乐和风格轮换，支持同图局部放大与直接交成片。明确无字任务仍保留无字。"
---

# FLASH CAST 视觉设计与视频专业 Skill

本部门的现行入口；老板截至2026-10-10的已确认制作偏好集中在此及下列引用，不再逐日追加相互覆盖的默认值。当前任务明确要求优先，真实性、安全和准确外部授权边界不变；本项目偏好高于通用 Skill 的默认皮肤、角标和历史样例。

## 开始前与职责边界

- 读取 `AGENTS.md`、本部门 README、注册表中本部门条目、路由规则、七份公司确认资料、相关 brief/原任务回执。
- 读取 `skills/flashcast-department-learning/SKILL.md`、本部门活动学习记录；`retired_lessons`只供指定历史复现，不加载为新任务默认，有`supersedes`的新经验优先。
- 任务只要整理 Skill 或方案时，不额外生成图片/视频；明确制作或返工才进入生产。输出在本项目 `drafts/creative/<task_id>/<run_id>/`、`delivery/creative/<task_id>/<run_id>/`，不写共享 Skill runtime。
- 按 `playbooks/department-system-current.md` 的动态注册角色与 `playbooks/department-daily-professional-loop.md` 执行。先续原任务、QA最小返工和依赖齐全事项；普通结果不向其他聊天发送、不打断active、不自行跨部门派工。
- 先在本固定聊天非空回报，再按真实回执冻结V2、唯一入队及回读；缺原生回执只能如实保留待补，不伪造。停止必列未完范围、唯一负责人、下一动作和解除条件。不扩展生产许可。

只使用注册表的4个生产子 Skill：`full-house-custom-ad`（行业总导演）、`imagegen`（空间/封面素材）、`hyperframes`（正式最终时间线）、`media-use`（媒体冻结与来源）。本地脚本与封面描述词模块不是额外子 Skill。技能维护按当前用户授权，不扩展生产白名单。

## 六类产品，共用文字和封面方法

| 用户需求 | selected_product_type | 正片的信息任务 |
| --- | --- | --- |
| 高真实感空间广告 | `realistic_effect_ad` | 讲明设计亮点，常规版本有简洁双语说明 |
| 橱柜、衣柜、电视柜工艺 | `cabinet_detail_explainer` | 用可见结构和同源细节解释做法，不编造性能 |
| 装修避坑知识 | `renovation_mistake_guide` | 一个具体问题、判断与改善办法 |
| 设计方案讲解 | `design_plan_pitch` | 风格、柜体、收纳、动线和材质的设计逻辑 |
| 品牌服务流程 | `brand_process_ad` | 已确认的服务阶段、交付物和检查方式 |
| 同房间改造对比 | `concept_before_after` | 同房间、同视角、同边界，解释实际变化 |

六类有字视频全部读取 [正文文字系统](references/premium-typography-system.md) 和 [封面设计](references/approved-cover-design.md)，不另建分类字体/封面皮肤。统一的是双语层级、对齐、克制浅底与画面保护，不是每片相同文案、坐标、照片、透明度或转场。

`input_mode` 仍区分自主、参考、授权素材与campaign；`presentation_mode` 在文案生成前决定。常规知识/方案/工艺/流程/对比用 `copy_led` 或必要轻注释；明确“无文案/只看空间”才锁定 `visual_music/copy_mode=none`，不强加正文。有字的封面、标签、说明、改前/改后、CTA和片尾均配对英语；品牌专名不乱译。

## 必读规则与唯一职责

| 需要作出的决定 | 唯一现行规则 |
| --- | --- |
| 通用档位、批次、代表帧与QA晋级 | `$full-house-custom-ad/references/adaptive-production-core.md` |
| 五类知识深度、48场景、跨类型选题去重与实际采用 | [装修知识工作流](references/renovation-knowledge-workflow.md) |
| 24风格顺序、来源和档位差异 | [项目叠加规则](references/adaptive-renovation-workflow.md) |
| 正文字体、语言、位置、密度与阅读节奏 | [正文文字系统](references/premium-typography-system.md) |
| 独立封面创意、文字层级、浅底细框与双画幅 | [封面设计](references/approved-cover-design.md) |
| 保留全景的同源局部放大、分辨率与定位 | [同图局部细节](references/same-image-detail-lens.md) |
| 全部文案、风险词库、右侧轻抖、合并发布描述 | [抖音发布包](references/douyin-publish-package.md) |
| 适配随机音乐、实际使用账与参考视频 | [音乐工作流](references/music-first-reference-workflow.md) |
| 目录与合同、机器检查和唯一负责助理独立验收边界 | [生产合同](references/production-contract.md)、[QA门](references/qa-gates.md) |

自主或参考任务再按需读取 [自主创意](references/autonomous-renovation-workflow.md) 与 [技能路由](references/skill-routing.md)。不为了简单字幕返工重新学习全部平台或重新分析未变素材。

调用示例统一在 `prompts/renovation-video-request.md`。活动知识、实际使用账与历史归档的身份由 `data/knowledge/full-house-custom-knowledge-manifest.json` 区分：旧主题库/提示词已退出生产路径，备份不参与默认加载。共享风格辅助函数仍被使用，不等于允许调用旧选题CLI。

## 当前制作默认

- 抖音：一条完整MP4，1080×1920、9:16满屏，不留上下空白；未另指定时不超过30秒。先适配随机选库内音乐，按实际乐句和双语阅读量确定图片数/时长，不固定12秒、不拆成三条、不盲目堆图；全屋内容覆盖本条承诺的空间。
- 音乐全库制作使用决定 `owner-all-library-music-use-20261007` 覆盖现有及未来通过解码、完整性和去重检查的新曲。适配后随机去重，不逐首确认；独立版权字段原样保留，不因unknown阻断已授权配乐制作。同任务返工保留已选曲，不重复追加挂载历史。
- 未指定风格的自动原创按24风格×3变体顺序轮换；先读取项目账并peek，实际采用后只commit一次。指定风格和同任务返工不重复推进；三条品牌线只是创意参考，不让方案片每次都变成意式极简。
- 图片cover满屏且不拉伸。先突出家具、柜体和空间关系，不为了放字制造大片地板/天花。主照片稳定，禁止整图持续推拉/平移/Ken Burns；转场按内容和构图逐对选择，不套房间名特效表。
- 逐镜检查曝光、白平衡、材料和相邻镜头；合格原图可保留。不能用全片泛黄、压暗、发灰、强锐化制造高级感。具体方法按需读通用 Skill 的 `transition-language.md`、`filter-color-system.md`。
- 讲到柜体、抽屉等可见细节时，优先保留同一全景并显示同源裁切放大窗；不擅自切成另一张生成近景。定位框/短引导线有解释用途，放大窗与字幕各自避让家具和彼此，进—停—退后回到干净全景。
- 正文深炭灰中文宋体短主题＋常规无衬线英文，主题与说明分时；自然空地优先，必要时小面积中性浅白半透明衬底。封面独立规划，统一“小分类→短中文主题→英文解释”的阅读轴、深墨黑字、淡石白局部半透明衬底和克制细框；不加阴影/模糊，不损原图清晰度。
- 封面先写brief和描述词再生成/排版，可独立设计底图，不强制截正文、竖排或固定女性人物。9:16首帧和同构3:4主封面逐图检查；第0帧封面，第1帧回正文，除非当前任务明确另有要求。
- 默认不加“概念改造演示/仅设计效果图/AI设计”等制作角标；内部来源如实记录，不冒称实拍完工。发布描述只讲设计和使用价值，不写制作方式或免责声明；平台生成内容标记由老板发布时处理，不记为已经设置。

## 执行到交付

通用生产核心保持一个；本项目的执行清单如下：

1. 锁定需求、真实性、六类中的本条信息任务、当前档位和素材范围。抖音直接成片默认按 `publish` 准备完整本地交付包；`publish` 不代表已发布。明确内审用 `preview`。
2. 除固定品牌流程外，先读装修知识工作流与manifest，运行项目renovation_knowledge.py peek：选五类适用深度卡、严格空间范围、近期跨类型去重及当前风格。全屋用whole_home组合，不拿一张细节卡冒充整屋；选题耗尽先在已授权范围研究新卡，不重置账本。冻结selection并在content-plan写具体动作/镜头证据，生成图片前运行validate-plan。再选择原音乐流程的具体音乐，规划必要图片、细节窗、转场、颜色及≤30秒时间线。实际采用后用项目工具统一commit一次，不再用旧commit重复推进。旧版文字/封面返工保留未授权调整的照片、音乐、切点和时长。
3. 先定稿全部中英字幕、封面文字、口播（如有）、双语描述及中文/英语两套话题，每套正好5个。中文只固定 `#马来西亚装修公司`，其余4个按本条内容安排；英语版逐项对应，采用自然的马来西亚行业说法。两套全部同批真实轻抖检测，详细字段和固定英语对应以抖音发布包为准。
4. 只在右侧内置浏览器操作轻抖，不打开Google Chrome。真实命中按证据去重入风险库，改写后整包复检；当前整包无命中、证据/哈希经执行者实核即可继续，不问老板是否看过截图。视觉返工且文字完全未改时按发布包规则引用原检测时间，不伪称新检测。
5. 先做代表帧内检，核原尺寸/360px字体、家具保护、衬底、细节同源与3:4/9:16封面。直接出片自行完成内检后继续；只有当前任务明确“先给图确认”才停在该确认点，不重复问已认可样式。
6. HyperFrames输出单条MP4，解码核帧0/1、逐镜/切点、稳定主图、图文对应、音视频流和≤30秒时长。最终文件与报告绑定本次run；检查未支持新组件时保留失败事实并补实际测量，不伪造全量PASS。
7. 给老板成片、可点击绝对文件夹地址，以及两份独立可复制文案：**同一中文描述＋英文描述＋5个中文话题**（`caption.txt`），以及**相同描述＋5个对应英语话题**（`caption-en-tags.txt`）。每份描述与话题合在一起，不拼成一条10话题文案。技术验证、内检、唯一负责助理独立验收和平台发布分别说清；不上传/发布。

`qc-report.json` 为机器证据，`qa-report.json` 是唯一聚合结论，handoff只引用当前聚合QA；同任务新run不能直接使用旧视频QA。可修复问题先在本范围修复并继续，事实/登录/授权等缺口只阻断依赖项，按实际解除条件说明。

## 已批准的方法参考与外部边界

六平台自然增长方法仅使用 `data/learning/visual-short-video-method-reference-v1.json` 清单内5份准确hash的静态资料，包 `flashcast-short-video-organic-methods-v1/method-reference-v1`，QA回执 `logs/department-outbox/fc-20260927-short-video-organic-skill-study-v1-method-reference-v1-qa.json`。真实流量效果须原生数据，不以学习、渲染或文件数量证明；原研究任务 `fc-20260927-short-video-organic-skill-study-v1` 保留历史。

统一发布方法入口 `skills/flashcast-unified-publishing/SKILL.md` 与 `playbooks/unified-social-publishing.md` 只用于已授权的本地准备；不是第五个生产子Skill、连接完成或外部发布许可。多平台完整文案另按准确任务整包检测，抖音单包不能冒充全集PASS。

不编造公司资质、案例、评价、价格、性能、尺寸或客户结果；不把静态图包装成真实连续漫游。不复制参考作品/素材；不保存密码、Token、Cookie等秘密。上传、账号连接、排期、投放、购买、收费服务和客户联系均需准确授权。先在本部门回报实际结果，再写outbox/report，最后记录有证据的部门学习；不修改其他项目或旧交付。
