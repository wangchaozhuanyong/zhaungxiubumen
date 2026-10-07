# FLASH CAST 装修视频叠加规则

通用状态机唯一来源是 `$full-house-custom-ad/references/adaptive-production-core.md`。本文件只定义 FLASH CAST 项目差异；发生冲突时按用户当前指令、真实性/安全、通用状态机、本文项目规则的顺序裁决。

## 1. 项目生产档位

- `preview`：内部快速看方向。必需 `source-brief.json`、`content-plan.json`、`storyboard.json`、`asset-manifest.json`、preview MP4、机器 `qc-report.json` 和 contact sheet；默认不要求 QA 聚合/handoff/发布包。老板要求检测或已规划发布文字时，仍执行全部文字整包检测，未核验只作内部审片。
- `candidate`：给老板/客户审片。在 preview 基础上增加 schema v2 `production-contract.json`、聚合 `qa-report.json`、`handoff-package.json`、关键帧和 provider audit。
- `publish`：在 candidate 基础上增加素材/音乐公开权利、视频描述、正好 5 个话题、两套封面、Qingdou 结果或带路径 blocker。
- `l4`：在 publish 基础上增加连续性报告、L4 专项评分、人工/AI 空间语义复核。

`qc-report.json` 是机器层；`qa-report.json` 是唯一聚合放行结论；`handoff-package.json` 只引用当前 `task_id/run_id` 的聚合 QA。禁止平行维护第二份“最终 QA”。

## 2. 知识、选题与风格

| 产品 | 项目必读 | 轮换规则 |
| --- | --- | --- |
| `renovation_mistake_guide` | `data/knowledge/renovation-mistake-knowledge-base-v1.json`、used topics、selector | 默认避开最近 30 支；最近 3 支轮换类别；高风险主题重新核对当前官方/专业来源 |
| `design_plan_pitch` | knowledge manifest、design used topics、selector | 15 类 120 条去重 |
| `concept_before_after` | knowledge manifest、concept used topics、selector | 12 类 96 条去重；同空间/同机位/同边界，至少改变两个设计维度 |
| 未指定风格 | `data/knowledge/whole-house-style-rotation.json`、rotation prompt | 24 风格 × 3 变体顺序轮换；采用后才 commit |

品牌三线：

- 意式极简主视觉：效果图广告、柜体工艺、设计方案、高端品牌主画面；
- 现代简约通用线：避坑、品牌流程、普适获客内容；
- 法式奶油轮换线：概念改造和生活方式细分。

2026-10-07老板要求每条自动原创视频依次换风格。现行优先级：当前明确风格/已锁定真实客户brief > 真实性/现场功能 > 未指定风格的24风格自动队列 > 三线创意参考。旧“三线策略高于自动轮换”在本项目已覆盖；三线不再按产品类型强制把方案片锁为意式极简。风格差异必须落实到柜门、材料、五金、配色、灯光和空间节奏；只换滤镜不算轮换。

从 `$full-house-custom-ad` 的实际目录运行 `scripts/knowledge_rotation.py peek --product-type <本次类型> --state-dir <PROJECT_ROOT>/data/knowledge`，不得省略项目状态目录或只凭记忆选择。按现有队列依次使用24风格的V1，再轮到各风格V2、V3；72个风格/变体组合并不是72种独立风格。真实空间不适用时记录跳过理由，不能偷偷重置指针或总回到意式极简。

只有实际进入确认方案或成片的自动选择才使用 `commit`，显式带本次 `task_id/topic_id/style_id/variant_id` 与项目 `state-dir` 校验，先核使用账避免重试重复推进。用户指定风格记录为explicit：不等于队列下一项时不推进自动队列；候选、被否决图和未采用预览不消耗。当前历史是否登记以账本为准，不能将规则存在说成旧视频均已轮换，不为本次核验补写消费记录。

## 3. 精确真实性披露

AI 概念/效果图必须在 `source-brief.json` 中声明来源属性；画面默认不显示 `仅设计效果图` 字样，默认示例不启用该角标：

```json
{
  "source_tier": "ai_concept",
  "compliance_overlays": []
}
```

仅在本批次确需真实性披露时，才加入以下左下角角标；`persistent=true` 只适用于已按此条件启用的披露，不是默认显示开关：

```json
{
  "source_tier": "ai_concept",
  "compliance_overlays": [
    {
      "text": "仅设计效果图",
      "role": "truthfulness_disclosure",
      "placement": "bottom_left_safe_zone",
      "persistent": true
    }
  ]
}
```

默认无角标不改变概念来源事实，不得隐瞒来源或把概念图宣称为真实案例。显示 `仅设计效果图` 时，按老板最新要求仅放在左下角角落，使用低干扰小字、无显眼底板，避让家具；各画幅独立定位。公开发布前仍须核验真实平台遮挡与必要真实性披露，内部角落小样不代表发布放行。

不得改写为 `AI设计`。概念改造片另加 `概念改造演示`。这些字段是 `compliance_overlay`，不属于 `visual_music/copy_mode=none` 所禁止的内容文案；除此之外不得自动加入标题、英文、字幕、价格、电话或 CTA。

## 4. 抖音发布文字与正式封面（publish/l4）

完整规则读取 [抖音发布文字与封面包](douyin-publish-package.md)。2026-10-02最新要求：所有实际公开文字（含口播时的全文）先完整规划，加载 `data/knowledge/qingdou-risk-lexicon.json` 避用历史命中词，再由 `public_copy_guard.py prepare` 汇总一份完整文案一次送轻抖；真实命中由 `record` 带证据去重入库。任一字改动须整包复检，不分项零散检测。只有内部画面小样且没有公开发布文字时可标not_applicable；不得称小样文字已经轻抖通过。正好 5 个话题中固定包含 `#马来西亚装修公司`、`#马来西亚全屋定制`，另 3 个按内容主题、空间/风格和本地服务意图选择。

封面同时交付 1080×1440 的 `cover-3x4.png` 和同构的 1080×1920 `first-frame-cover-9x16.png`。前者用于抖音封面选择，后者放入 HyperFrames 最终时间线第 0 帧；第 1 帧立即回正片。只有当前批次有书面 `in_video_cover_opt_out`、原因和证据时可不嵌入。安全区预览不是正式封面。

先读取 `$full-house-custom-ad/references/cover-director-prompts.md`，规划主题/人物/家具/文字区并保存brief与prompt后生成。封面视觉必须匹配实际视频，不能把示例现代攻略标题套进意式片。

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
