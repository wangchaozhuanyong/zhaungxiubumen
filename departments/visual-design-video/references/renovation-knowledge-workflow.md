# 装修知识与内容轮换：项目唯一入口

2026-10-08老板指出内容重复，要求扩充除固定品牌流程外的五类视频。本文件覆盖旧项目选题入口，不改变文字、封面、音乐、成片或发布流程。

## 0. 选题内容边界

老板2026-10-14明确：以后只讲装修过程中如何设计、哪里怎么做以及使用痛点，不讲签合同的坑或对付装修公司。此为本项目所有视频分类、知识学习与每日100期的共同内容定位，不外推到其他项目或业务资料。

- 内容主角必须是具体空间、部位、材料、设备、施工顺序或生活动作。讲清“哪里容易做错→为什么不好用/容易出问题→怎样设计或正确处理→如何观察判断”，至少给出两个不同的改善或专业核验动作及对应画面。
- 不制作装修公司选择/防套路、比较报价及增项费用、合同条款、付款节点、压价谈判、索赔投诉或对抗施工方的选题；封面、口播、字幕、描述及话题都不能把设计做法改写成这种叙事。换成中性标题而内容仍讲合同/费用，不算符合。
- 允许讲防水、排水、墙面、柜体收口、门窗、设备预留、施工顺序、材料适用性和成品使用检查；准确指出做法问题，不掩盖缺陷，也不把专业安全核验删掉。专业者检查是保障正确做法，不是“对付公司”；仍按原资料/地区/型号与安全边界，不输出无依据的危险DIY或施工参数。
- 固定品牌流程只讲公司已确认的设计、施工协调和交付步骤，不借流程扩展成合同防套路。材料投入可以围绕使用价值选择，不转成报价博弈。
- 研究和准入新卡时先做上述内容筛选，再查来源、去重、写文案。旧合同/报价卡只保留历史及准确旧任务追溯，不作为新任务候选；机器排除清单统一在 `data/knowledge/full-house-custom-knowledge-manifest.json` 的 `content_policy`，选择器对新任务及显式topic-id同样执行。已实际采用的原任务返工不改写原消费历史。
- 100期只调整未制作项，保留期号、task_id、排序和原消费账。已做E001保留历史，不重播、不再作为新内容方向；新替换题仍是待研究编辑题，不冒充已准入、已检测或已完成。

## 1. 先锁范围，不能只换风格

实际入口 `data/knowledge/full-house-custom-knowledge-manifest.json`。活动库为 `data/knowledge/renovation-scenario-library-v2.json`，准确场景、深度卡、来源及整屋组合数量以manifest/verify为准，不把初版数量当上限。卡中的具体布局是原创设计推导，不是厂家原文、工程认证或已验证业务结果。

- 覆盖住宅空间、家务与特殊需求、特殊家庭、材质/灯光等设计问题、围护机电需求和商用空间。场景表列出准确覆盖及未覆盖范围，不宣称已经穷尽装修行业。
- 新片只加载活动库，不从旧主题线索选择。旧避坑库与重复提示词已移出活动目录，归档映射在manifest的retired_assets_index；共享通用题库留给未迁移项目，本项目不加载。历史线索、编辑排期不与活动深度卡相加，跨类型适配、整屋组合、风格与变体也不另计知识点。
- 品牌流程 `brand_process_ad` 不进入知识轮换，继续只用公司已确认流程。其他空间主题不能增加公司未经确认的商业服务、资质、价格、案例或性能。
- 用户指定房间/问题时严格筛选；自动住宅内容不突然变成咖啡店或办公广告。商用需求显式 `--context commercial --scene salon` 等，未指定的普通空间用 residential，确需跨行业研究用 any。
- “全屋”不能只选一个局部卡。使用 whole_home组合：一条主命题配3至7个必要空间，门窗、材料和生活需求保持一致，≤30秒只讲清2至3个重点。8组合是组合方法，不是8种新风格。

## 2. 五类调用与内容密度

运行项目本地工具 `departments/visual-design-video/scripts/renovation_knowledge.py`：

```bash
python3 departments/visual-design-video/scripts/renovation_knowledge.py verify
python3 departments/visual-design-video/scripts/renovation_knowledge.py peek \
  --product-type design_plan_pitch --scope whole_home --task-id <真实任务ID>
python3 departments/visual-design-video/scripts/renovation_knowledge.py peek \
  --product-type cabinet_detail_explainer --scene dining --task-id <真实任务ID>
python3 departments/visual-design-video/scripts/renovation_knowledge.py peek \
  --product-type design_plan_pitch --context commercial --scene salon --task-id <真实任务ID>
```

peek只读；冻结其完整输出为本任务 `knowledge-selection.json`。未指定风格返回当前24风格队列的真实下一项；指定风格带 `--style-id Sxx --variant-id Vx`，不推进自动队列。风格不能压过房间功能。

| 产品 | 必须讲清 | 不能代替内容的做法 |
| --- | --- | --- |
| 空间展示 | 使用需求＋2至3处具体设计亮点 | 只报房间名、风格名或“高级感” |
| 柜体细节 | 物品、可见取放结构、为什么这样安排 | 用闭合柜门虚构抽屉/五金性能 |
| 避坑 | 一个问题、两步改善或核验、适用条件 | 一片堆很多标题或制造绝对结论 |
| 方案 | 日常需求对应布局、归置、材料/光线理由 | 只换颜色、图片和滤镜 |
| 改造 | 同房间同机位，至少两个独立可见变化 | 换房间、偷改尺寸或只换材质当两项变化 |

每卡必须有具体问题、至少两个不同设计动作、判断方式、画面证据、适用边界和来源范围。对白须提炼为短中英双语，不把整张卡塞进30秒视频。保留无字观看时间，使用当前统一文字、封面和同源细节窗方法。

## 3. 跨类型去重与实际采用

- 默认避开最近30个已用语义命题，跨五类共同去重。去重对象是场景＋问题＋解决命题，不是标题、风格或图片文件名。
- 优先未用卡；候选充足时避开最近3个类别、4个场景。明确空间会缩窄范围；软窗口必须在selection中记放宽理由，不能偷偷扩大到其他房间。
- 旧使用账与已检查旧成片通过准确映射只读参与近期过滤；不补造新库历史消费。新库全量旧消费是否可映射须如实记录，当前映射只覆盖已核验条目。
- 同任务返工传同一task_id，返回已采用主题/风格。预选、模拟、知识学习、未采用图片与被否决方案都不消费。
- 近期候选耗尽时返回明确原因；在当前已授权内部任务中研究并补充准确新卡后重试，不重置历史、不假称新选题、不由同义改写绕过去重。缺场地事实或产品资料只阻断依赖该事实的结论，可转为不依赖它的原范围设计表达。

实际确认方案或实际渲染成片后，采用工具仅登记一次：

```bash
python3 departments/visual-design-video/scripts/renovation_knowledge.py commit \
  --task-id <真实任务ID> --selection <本任务knowledge-selection.json绝对路径> \
  --adoption-kind rendered_video --evidence <本任务adoption-evidence.json绝对路径>
```

证据有task_id/topic_id、adoption_status=rendered_video、实际video_path/video_sha256及当前qc_report_path。确认方案则使用confirmed_plan，证据有owner_confirmed_plan及真实owner_confirmation_ref。字段存在不替代原生确认或视频验收，执行者须核实。

该commit同时登记内容与适用的自动风格队列，带输入指纹、项目内锁和事务恢复记录；重试不二次推进。禁止再对同一任务调用旧knowledge_rotation.py commit。异常prepared事务先检查，再用recover完成原准确事务；peek不擅自修账。指定风格只登记内容，不改自动风格指针。音乐推荐/挂载仍由原独立流程处理。

## 4. 生成图片前的内容检查

在content-plan.json增加knowledge_plan：

```json
{
  "selection_path": "drafts/creative/<task_id>/knowledge-selection.json",
  "selection_sha256": "<实际哈希>",
  "primary_topic_id": "<本条卡ID>",
  "design_actions": ["<卡中动作1>", "<卡中动作2>"],
  "shot_evidence": [
    {"action": "<卡中动作1>", "scene_id": "scene-1", "show": "<具体可见的家具与使用关系>", "mode": "full_view"},
    {"action": "<卡中动作2>", "scene_id": "scene-2", "show": "<具体可见的结构与物品归置>", "mode": "same_source_crop"}
  ],
  "supporting_topic_ids": ["<整屋才需至少3个有效关联卡>"],
  "same_room_camera_locked": true,
  "changed_dimensions": ["<对比片实际维度1>", "<实际维度2>"],
  "boundary_handling": "<如何避免未核验性能与工程结论>",
  "unverified_performance_claims": []
}
```

选题、分镜和文案形成后运行：

```bash
python3 departments/visual-design-video/scripts/renovation_knowledge.py validate-plan \
  --plan <本任务content-plan.json绝对路径>
```

该检查只确认计划输入、具体动作、镜头对应和范围，不证明生成图已符合、不证明轻抖/独立QA/发布通过。代表帧仍逐图检查两个动作确实可见。五类均保留本检查；固定品牌流程明确NOT_APPLICABLE，不重新轮换。

## 5. 研究与来源更新

- 优先主管部门、制造商技术资料和原设计机构项目说明。来源只支持其准确范围：设计推导标designer_synthesis，不能改写为法规或产品实测。
- 电气、结构、防水、燃气、消防、许可、健康、安全及性能，实际使用前重新核准确原始来源和所在地/型号，必要专业复核；没有依据改为需求/核验方法，不出可执行施工参数。
- 本次Dulux页面读取失败，搜索摘要未升级为已核验正文，也未入18个来源计数；墙面卡只保留设计与查因，不生成配比和干燥时间。其它国外资料同样不当马来西亚规范。
- 新场景出现或候选池不足时：查现有卡→找专业主来源→写原创具体动作与可见镜头→标边界/日期/来源→verify与去重模拟→接入原任务。不要新增自动任务、收费插件、账号连接或下载他人作品。
- 老板本次明确授权的100期系列按 [每日系列](daily-renovation-video-series.md) 研究全装修领域并逐期制作；这是编辑排期，不是第二个生产知识库。每期来源/动作核验后才准入活动库，以 `peek --topic-id <准确卡ID>` 冻结，依然遵守范围与近期语义去重；该字段不能强行重用近期卡。其他研究任务仍不自行创建定时任务。
- 本库不等于轻抖已检。真正将用于视频/封面/口播/描述/话题的全部中英文文本仍一次整包轻抖检测；无命中实核后直接制作，不问老板截图确认。

本次只更新知识/调用，不更改已交付六条MP4、固定品牌流程、音乐库/使用账或当前风格指针。

## 历史与恢复

旧使用账仍在原路径，只读用于准确映射与去重；未能映射的旧主题不能编造新消费。已停用学习记录放retired_lessons，不作为新默认。原文件与哈希见 `backups/fc-20261008-visual-skill-cleanup-v1/retirement-index.json`；仅复现旧任务时按映射读取，不自动还原到活动目录。共享旧脚本只供新选择器导入风格辅助函数；直接对本项目运行旧peek/commit会拒绝，不会改账。
