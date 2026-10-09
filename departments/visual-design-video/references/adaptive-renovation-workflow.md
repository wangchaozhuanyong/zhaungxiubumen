# FLASH CAST 装修视频叠加规则

通用状态机唯一来源是 `$full-house-custom-ad/references/adaptive-production-core.md`。本文件只定义FLASH CAST项目差异：当前明确指令及真实性/安全优先，已确认的项目制作偏好覆盖通用默认与历史样例；档位、批次和QA晋级仍沿用通用核心，不建立平行状态机。正文、封面、局部放大分别只由 `premium-typography-system.md`、`approved-cover-design.md`、`same-image-detail-lens.md` 管理。

## 1. 项目生产档位

- `preview`：内部快速看方向。必需 `source-brief.json`、`content-plan.json`、`storyboard.json`、`asset-manifest.json`、preview MP4、机器 `qc-report.json` 和 contact sheet；默认不要求 QA 聚合/handoff/发布包。老板要求检测或已规划发布文字时，仍执行全部文字整包检测，未核验只作内部审片。
- `candidate`：给老板/客户审片。在 preview 基础上增加 schema v2 `production-contract.json`、聚合 `qa-report.json`、`handoff-package.json`、关键帧和 provider audit。
- `publish`：在 candidate 基础上增加素材/音乐公开权利、视频描述、正好 5 个话题、两套封面、Qingdou 结果或带路径 blocker。
- `l4`：在 publish 基础上增加连续性报告、L4 专项评分、人工/AI 空间语义复核。

`qc-report.json` 是机器层；`qa-report.json` 是唯一聚合放行结论；`handoff-package.json` 只引用当前 `task_id/run_id` 的聚合 QA。禁止平行维护第二份“最终 QA”。

## 2. 知识、选题与风格

五类选题与内容密度唯一规则为 [装修知识工作流](renovation-knowledge-workflow.md)，知识及来源只加载manifest指定活动库。固定品牌流程不入轮换；旧主题与重复提示词已退出活动路径，历史使用账只读去重。

风格优先级：当前明确风格/已锁定客户brief > 真实性/现场功能 > 未指定风格的24风格自动队列。三条历史品牌线仅在指定创意研究/旧片复现时作参考，不按产品类型固定分配。风格差异至少落实到柜门、材料、五金、配色、灯光和空间节奏中的5项；只换滤镜不算轮换。

项目 `departments/visual-design-video/scripts/renovation_knowledge.py peek --product-type <本次类型> --task-id <真实任务ID>` 同时只读返回知识与当前风格；全屋加 `--scope whole_home`，指定商用或空间按知识工作流筛选。风格仍使用原project state-dir队列，不凭记忆或固定例值选择。按现有队列依次使用24风格的V1，再轮到各风格V2、V3；72个风格/变体组合并不是72种独立风格。真实空间不适用时记录准确理由，不偷偷重置指针。

只有实际进入确认方案或成片才使用项目工具 `commit`，带真实task_id、冻结selection和采用证据，登记内容与适用的风格一次；同任务返工不二次推进。指定风格为explicit，不推进自动队列；候选、被否决图、模拟与未采用预览不消耗。禁止对同一新任务再运行旧knowledge_rotation.py commit。当前历史以账本为准，旧账只读，不为本次学习补造消费。

## 3. 内部来源与画面标记

AI 概念/效果图必须在 `source-brief.json` 中声明来源属性；画面默认不显示 `仅设计效果图` 字样，默认示例不启用该角标：

```json
{
  "source_tier": "ai_concept",
  "compliance_overlays": []
}
```

六类均默认无制作角标：不添加 `概念改造演示`、`仅设计效果图`、`AI设计`，也不换同义说明。内部来源如实保留，不宣称真实完工/客户案例。发布描述只讲设计与使用价值；平台生成内容标记由老板发布时设置，不记为已完成。只有当前任务明确要求或准确发布场景确有必要的披露才另规划中英内容、低干扰位置并纳入整包检测；这不是恢复历史常驻角标的开关。无字正片仍不自动加入内容文案/CTA。

## 4. 抖音发布文字与正式封面（publish/l4）

完整规则读取 [抖音发布文字与封面包](douyin-publish-package.md)。2026-10-02最新要求：所有实际公开文字（含口播时的全文）先完整规划，加载 `data/knowledge/qingdou-risk-lexicon.json` 避用历史命中词，再由 `public_copy_guard.py prepare` 汇总一份完整文案一次送轻抖；真实命中由 `record` 带证据去重入库。任一字改动须整包复检，不分项零散检测。只有内部画面小样且没有公开发布文字时可标not_applicable；不得称小样文字已经轻抖通过。正好 5 个话题中固定包含 `#马来西亚装修公司`、`#马来西亚全屋定制`，另 3 个按内容主题、空间/风格和本地服务意图选择。

封面同时交付 1080×1440 的 `cover-3x4.png` 和同构的 1080×1920 `first-frame-cover-9x16.png`。前者用于抖音封面选择，后者放入 HyperFrames 最终时间线第 0 帧；第 1 帧立即回正片。只有当前批次有书面 `in_video_cover_opt_out`、原因和证据时可不嵌入。安全区预览不是正式封面。

先读取 `$full-house-custom-ad/references/cover-director-prompts.md`，规划主题/人物/家具/文字区并保存brief与prompt后生成。封面视觉必须匹配实际视频，不能把示例现代攻略标题套进意式片。

正文与封面均中英双语，分别按现行设计模块规划，描述与5个中文话题合并给老板。完整整包真实无命中、对应截图与当前哈希经执行者实核后直接继续，不等老板确认。视觉返工且文字未改按发布包规则保留真实原检测时间；不复制旧视频QA放行新成片。

9:16 1080×1920 旧版保守基线（`legacy_four_sides`，非官方像素规范）：

- 顶部预留至少 240px；
- 底部预留至少 420px；
- 右侧互动区预留至少 180px；
- 左侧至少 96px；
- 关键文字和主体集中在 3:4 主封面；映射到 9:16 首帧时位于居中裁切 `y=240..1680`。

老板本批明确“只考虑上下，不考虑左右”时，采用 `safe_zone_policy=vertical_priority_owner`：顶部420px、底部600px，文字位于 `y=420..1320`；左右UI不占位，只保留审美留白。报告须绑定本批task_id与 `layout_authorization.explicit_user_instruction=true` 和真实指令证据。不得冒称官方安全区；其他批次不继承本次豁免，发布前须重新核对原生预览。图片仍满屏出血，不把预留区做成黑白空带。

运行：

```bash
python3 departments/visual-design-video/scripts/validate_cover_safe_zone.py \
  delivery/creative/<task_id>/publish-cover-report.json \
  --out delivery/creative/<task_id>/cover-validation.json

python3 departments/visual-design-video/scripts/validate_douyin_publish_package.py \
  delivery/creative/<task_id>/publish-package.json
```

未进入 publish/l4 且确实没有公开发布文字时，Qingdou和发布封面可以标 `not_applicable`；若已交付抖音字幕、描述、话题等可发布文字，仍执行上文整包检测或如实HOLD。不得为了过门给无字正片强加正文。

## 5. 项目验证

计划/代表帧/候选分别运行：

```bash
python3 departments/visual-design-video/scripts/validate_renovation_workflow.py \
  drafts/creative/<task_id> --phase plan

python3 departments/visual-design-video/scripts/validate_renovation_workflow.py \
  drafts/creative/<task_id> --phase frames

python3 departments/visual-design-video/scripts/validate_renovation_workflow.py \
  drafts/creative/<task_id> --phase final
```

`preview` 只能运行 plan/frames，不能使用 final 阶段。`final` 阶段要求 candidate/publish/l4 的聚合 QA 引用机器 QC，并实测最终 MP4 音视频流、逐镜色彩、代表帧、联系表和持续整图运动。

验证 PASS 只表示可进入相应档位的内部交接，不代表已上传、发布或投放。
