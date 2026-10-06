# FLASH CAST 图片与视频生产合同

通用状态机、档位定义和 Provider 规则来自 `$full-house-custom-ad`。本文件只说明 FLASH CAST 的项目目录、合同字段和验证边界。

## 任务目录与身份

正式任务写入 `drafts/creative/<task_id>/`，交付写入 `delivery/creative/<task_id>/`。所有机器合同使用同一个 `task_id/run_id`；返工创建新 `run_id` 并记录父版本。禁止写入共享 Skill runtime 的 `output/`。

`source-brief.json` 必须先于文案字段记录：

- `production_profile`：`preview/candidate/publish/l4`；
- `input_mode`、`video_need`、`presentation_mode`、`copy_mode`；
- `source_tier`、`authenticity_label`、目标渠道、比例、时长；
- 素材范围、授权、不能假设的公司事实；
- AI 概念/效果图的 `compliance_overlays`，精确字样为 `仅设计效果图`。

真实性披露不是内容文案。`visual_music/copy_mode=none` 禁止标题、正文、英文、字幕、旁白和视频内 CTA，但允许合同已声明的 `compliance_overlay`。

## 档位文件

| 档位 | 最低文件 |
| --- | --- |
| `preview` | `source-brief.json`、`content-plan.json`、`storyboard.json`、`asset-manifest.json`、preview MP4、`qc-report.json`、contact sheet |
| `candidate` | preview 全部 + schema v2 `production-contract.json`、`quality-stack-report.json`、provider audit、`qa-report.json`、`handoff-package.json`、关键帧 |
| `publish` | candidate 全部 + `publish-package.json`、视频描述、正好 5 个话题、素材/音乐权利状态、`qingdou-report.json` 或 blocker 证据、3:4 主封面与 9:16 首帧适配图 |
| `l4` | publish 全部 + 连续性报告、L4 专项评分、人工/AI 空间语义复核 |

按任务需要生成的人读 Markdown 可以存在，但不能复制一份平行机器合同。`visual_music` 不要求 `script-or-copy.md`；只有 `minimal_brand/copy_led` 才生成对应文字稿。

抖音 `publish/l4` 的 `publish-package.json` 以 [抖音发布文字与封面包](douyin-publish-package.md) 为准：固定包含 `#马来西亚装修公司`、`#马来西亚全屋定制`，另外三个话题按本条内容选择；Qingdou 必须覆盖屏显、封面、描述和话题四类公开文字，任一修改都要重新检查。

## QA 权威关系

- `qc-report.json`：原始机器检查；包含音视频流、时长、尾音、亮度、字幕、稳定运动和最终 MP4 帧级分析。
- `qa-report.json`：唯一聚合结论；通过 `automated_evidence.video_qc` 引用 qc，并汇总代表帧、逐镜色彩、人工审片、音乐四态、权利和 blocker。
- `handoff-package.json`：只引用当前聚合 QA 已放行的最终文件与哈希；handoff 不代表发布。

机器 QC、人工 QA、Reality Checker 和生产发布是不同状态，不得相互冒充。

## 代表帧、调色与音乐

完整渲染前用 `runtime/frame-review.json` 覆盖开场、最亮、最暗、材质和转场中点，并绑定 storyboard SHA-256。每个 scene 有独立 `grade_target`；先校正曝光/白平衡/材质，再匹配相邻镜头，最后克制风格化，禁止全片统一暖黄或暗电影滤镜。

`visual_music` 使用 `music-selection.json` 和 `music-map.json`；`selected/mounted/audible/rights_cleared` 分开记录。公开使用权未证明时只能停在 preview/candidate 或 HOLD。

## 机器验证

```bash
python3 departments/visual-design-video/scripts/validate_video_contract.py \
  drafts/creative/<task_id>/video-contract.json

python3 departments/visual-design-video/scripts/validate_renovation_workflow.py \
  drafts/creative/<task_id> --phase plan
```

代表帧用 `--phase frames`；candidate/publish/l4 完成聚合 QA 后用 `--phase final`。`preview` 不允许 final 阶段。

验证通过表示当前档位资料一致，不等于允许上传、发布、投放、购买或联系客户。
