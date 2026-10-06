# FLASH CAST 抖音发布文字与封面包

本规则覆盖抖音视频的全部公开文案。2026-10-02老板要求优先于旧“只在publish/l4检测”的节流：只要要交付可直接用于抖音发布的字幕、封面、口播、描述或话题，就先完整规划，统一一批送轻抖。没有发布文字的纯内部画面小样不强加文案，但不得称其文字“轻抖已通过”。完整发布门禁仍在 `production_profile=publish|l4` 启用；不增加自动上传、发布或收费权限。

## 1. 公开文字是一套，不是四次零散检查

每次发布必须把以下文字冻结为同一版本：

1. 视频内可见文字：字幕、工艺标注、材料标签、CTA 和真实性披露；
2. 封面文字；
3. 视频描述；
4. 正好 5 个话题。

有口播/旁白时，还必须提供 `spoken_copy_path` 指向全文；只读到字幕不算覆盖口播。视频文字包含片头片尾、品牌/联系方式、CTA、材料标注和“仅设计效果图”等披露。不得把内部制作说明、负面示例或整个storyboard当成公开文案送检；只汇总实际将显示或说出的文字。

全部文字写入 `publish-package.json` 引用的 UTF-8 文本文件，并计算同一 `public_text_sha256`。有口播时哈希同时覆盖 `spoken_copy`。任一字修改后，旧 Qingdou 结果立即失效，必须对修改后的整包重新检测，不零散补检。

Qingdou 必须覆盖 `on_screen_copy`、`cover_copy`、`video_description`、`hashtags` 四项，有口播另加 `spoken_copy`，并保存可核验截图或导出报告。无法访问、未登录、结果不完整或哈希不匹配时，状态只能为 `HOLD`，不得用本地关键词表冒充 Qingdou 或抖音平台审核通过。

### 1.1 先定稿，一次送检，命中后避用

执行顺序固定为：完整规划全部文字 → 加载项目风险词库、本地筛查 → 汇总一份 `public-text-batch.txt` → 一次提交轻抖 → 保存真实结果 → 命中入库并改写 → 有改字时整包复检 → 使用同版文字制作画面/配音和发布包。不要先分别检查字幕、描述、封面、话题；“一次”指同一完整版本一次提交，不是命中后永不复检。

生成图中的招牌/产品标签、品牌片尾及任何实际出现的文字也必须纳入规划清单；不能因为它们在图片里就跳过检测。成片后逐镜核对画面文字及实际旁白与送检版一致，必要时OCR辅助人工复核；新增或改动文字先更新整包再复检，不能继续使用旧PASS。

- 词库固定为 `data/knowledge/qingdou-risk-lexicon.json`。每条命中保存原词/短语、所在字段、检测时间、原因、建议改写、原任务/版本、统一文字哈希、送检文件哈希和真实结果证据哈希；按规范化词条去重，保留历次观察。
- 此库是“轻抖命中风险词/短语避用库”，不是宣称这些词在任何上下文都违法。未来公开文案一旦命中即先改写，不使用拆字、谐音或隐藏字符规避检测。事实错误不能只换词，应删掉或核实原承诺。
- 没有真实平台结果不编造命中词。初始化空库标 `DATA_MISSING_NO_VERIFIED_FINDINGS_IMPORTED`；单测合成命中只在临时夹具中使用，禁止写入真实词库。
- 本地筛查通过只叫 `READY_FOR_QINGDOU`，绝不是轻抖PASS。词库更新时重新做本地筛查；若文字及送检文件完全未改，可保留原轻抖证据，无须为词库版本变化重复平台检测。
- 若平台字数限制无法容纳整包，记录 `BLOCKED_QINGDOU_BATCH_LIMIT` 并处理合法整批入口，不自动拆成几次后声称一次完成。当前工具不联网、不登录、不代填轻抖结果。

先生成批次文件（输出目录必须是本项目本任务的新版本目录）：

```bash
python3 departments/visual-design-video/scripts/public_copy_guard.py prepare \
  delivery/creative/<task_id>/publish-package.json \
  --output-dir delivery/creative/<task_id>/copy-check-v1
```

把输出的 `package_binding` 写回当前版本的发布包：`copy_policy_version`、`public_text_sha256`、`public_text_batch_path`、`copy_guard_report_path`。如出现本地命中，先改完所有文字，再生成新版本整包；只有无命中才能提交轻抖。不要覆盖旧批次文件。

真实轻抖结果有命中时先准确人工转录 `findings`（`term`、`field`、`reason`、可选 `suggested_rewrite`），核对截图后入库：

```bash
python3 departments/visual-design-video/scripts/public_copy_guard.py record \
  delivery/creative/<task_id>/publish-package.json \
  --qingdou-report delivery/creative/<task_id>/qingdou-report.json
```

在规划定稿后、生成带可发布文字的画面/配音前，以及最终交付前，运行独立的文案门：

```bash
python3 departments/visual-design-video/scripts/public_copy_guard.py check \
  delivery/creative/<task_id>/publish-package.json \
  --out drafts/creative/<task_id>/runtime/copy-gate-<new_version>.json
```

`check` 只读核验当前整包、真实轻抖capture和最新避用库，不依赖尚未生成的封面/视频，也不修改词库、不再次提交轻抖。`PASS_COPY_ONLY` 只代表这一版文案门通过，不是整体QA、权利或发布放行。缺真实结果、漏口播/话题、改字、旧capture或新入库风险词均返回 `HOLD_COPY_GATE` 和非零退出码；只能继续明确标注未检测的内部审片，不交可发布版。`publish/l4` 仍须原完整发布包验证，不能用此门替代。需要登录或人机验证时由负责人手动完成，不读取凭证、不自动解验证、不自动付费。

`record` 校验当前完整批次、证据文件与哈希，并在真实入口拒绝显式 `SYNTHETIC_TEST_ONLY`、合成/夹具或 `provenance-test` 标记（含JSON及证据字节）。包、全部引用、报告/证据、词库和可控输出在任何对应读写前经本项目根目录与symlink规范化检查；直接函数调用与CLI使用同一边界。没有证据、漏字段、词不在提交内容内或旧版本命中均拒绝入库；重复录入幂等。入库不等于当前文案已通过，命中版本继续HOLD。

真实结果另须 `capture_review`：`status=personally_inspected_real_full_batch`、具名 `reviewer`、`reviewed_at`、`declaration=HUMAN_DECLARED_REAL_QINGDOU_FULL_BATCH`，并再次绑定当前 `task_id/run_id/public_text_sha256/batch_sha256/evidence_sha256`。这是执行者亲验同包轻抖capture的责任声明，不是机器截图鉴真，也不是权利、平台审核或发布许可。没有合成标记、JSON自洽、SHA一致或写了这个声明，都不能单独证明来源真实；必须亲验真实完整送检与对应结果再填写，不允许自动生成真实声明。无实际capture继续HOLD，不录活动词库。

测试只能显式提供函数 `sandbox_root` 或CLI `--test-sandbox-root`，且目录须位于该工具项目根内 `drafts/creative/`；词库和所有输入/输出也限定到该沙箱，不能借测试参数触及活动 `data/knowledge`。CLI测试使用沙箱 `fixture-risk-lexicon.json`（record可显式 `--test-lexicon`），此模式输出 `SYNTHETIC_TEST_ONLY`、验证成功也只叫 `PASS_SANDBOX_ONLY`，夹具条目来源为 `synthetic_test_finding`，从不叫 `qingdou_verified_finding`。无隐式环境开关，不得把测试模式当真实入口或发布门。

`visual_music/copy_mode=none` 可以把视频内内容文案标为不适用，但真实性披露仍要写进 `on-screen-copy.txt`；封面文字、视频描述和话题仍属于发布文字。

## 2. 视频描述

必须生成独立 `video-description.txt`，再与话题组合成 `final/caption.txt`。描述遵守：

- 先说本条视频真正展示的空间、工艺、设计判断或避坑价值；
- AI 概念/效果图不得写成真实完工、真实客户家或真实 Before/After；
- 只使用已确认的公司事实，不承诺固定价格、固定工期、百分百无增项、审批必过或未经证实的资质；
- CTA 克制且只有一个主要动作，例如“留言空间类型”或“预约量尺”；
- 描述正文不混入 `#话题`，话题由单独字段管理。

## 3. 五个话题

每条抖音发布包必须正好 5 个不重复话题。

固定话题：

- `#马来西亚装修公司`
- `#马来西亚全屋定制`

另外 3 个由当前视频自动选择，每条分别覆盖一个轴：

1. `content_topic`：当前内容主题，例如 `#装修避坑`、`#柜体设计`、`#全屋设计`；
2. `space_or_style`：当前空间、品类或风格，例如 `#定制衣柜`、`#厨房橱柜`、`#意式极简`；
3. `local_service_intent`：真实服务地区或本地意图，例如 `#吉隆坡装修`、`#雪兰莪装修`、`#吉隆坡全屋定制`。

三个自适应话题必须与本条画面和公司服务范围一致，不追无关热词，不使用重复近义词占位。`publish-package.json.adaptive_hashtags[]` 记录每个话题的轴和选择理由。

## 4. 两套封面画布

抖音发布包必须同时生成：

- `cover-3x4.png`：1080×1440，作为抖音封面选择和主页裁切的主设计；
- `first-frame-cover-9x16.png`：1080×1920，作为视频第 0 帧；中间 `y=240..1680` 必须与 3:4 主封面同构，并为上下区域补足可裁切背景。

关键标题、主体和品牌识别集中在 3:4 主画布中。先读 `$full-house-custom-ad/references/cover-director-prompts.md`，规划主题、成年人物表达/动作、家具关系和文字区，保存brief/prompt后生成；示例现代攻略不能替换实际意式主题。

9:16 旧版 `legacy_four_sides` 基线为顶部240px、底部420px、右侧180px、左侧96px。老板本批明确只考虑上下、不考虑左右时可选 `vertical_priority_owner`：顶部420px、底部600px，关键文字位于 y=420..1320、左右UI不占位；报告绑定本批task_id和真实老板指令，不能为过门任意切换。两套均为项目设计基线，不是抖音官方固定像素规范。公开发布前仍核对真实平台UI。另生成 `cover-safe-preview-9x16.png` 叠加裁切/遮挡线，只作QA，不得作为正式封面或视频首帧；图片满屏，不把上下预留区做成空白带。

封面文字同样进入 Qingdou。封面标题优先 8–14 个中文字符、最多两行，一眼说明主题，不使用夸张承诺；这是项目设计基线，不冒充抖音统一字数规则。

最终 MP4 第 0 帧使用 `first-frame-cover-9x16.png`，随后立即进入正片。发布包保存：

- 3:4 封面与 9:16 中心裁切的一致性报告；
- 正式 MP4 第 0 帧与 9:16 首帧适配图的 SSIM 报告；
- 实际 frame 0、frame 1 和包含 frame 0 的联系表。

## 5. 最低文件与验证

```text
publish-package.json
copy-check-v1/public-text-batch.txt
copy-check-v1/public-copy-guard.json
public-text/on-screen-copy.txt
public-text/cover-copy.txt
public-text/video-description.txt
final/caption.txt
qingdou-report.json
evidence/qingdou-result.png|pdf|json
cover-3x4.png
first-frame-cover-9x16.png
cover-safe-preview-9x16.png
publish-cover-report.json
cover-validation.json
```

`publish-package.json` 最小结构：

```json
{
  "schema_version": "1.0",
  "platform": "douyin",
  "production_profile": "publish",
  "task_id": "<task_id>",
  "run_id": "<run_id>",
  "on_screen_copy_path": "public-text/on-screen-copy.txt",
  "cover_copy_path": "public-text/cover-copy.txt",
  "video_description_path": "public-text/video-description.txt",
  "caption_path": "final/caption.txt",
  "hashtags": [
    "#马来西亚装修公司",
    "#马来西亚全屋定制",
    "#当前内容主题",
    "#当前空间或风格",
    "#当前本地服务意图"
  ],
  "adaptive_hashtags": [
    {"tag": "#当前内容主题", "axis": "content_topic", "reason": "<与本条内容的关系>"},
    {"tag": "#当前空间或风格", "axis": "space_or_style", "reason": "<与本条画面的关系>"},
    {"tag": "#当前本地服务意图", "axis": "local_service_intent", "reason": "<与真实服务范围的关系>"}
  ],
  "public_text_sha256": "<统一公开文字哈希>",
  "copy_policy_version": "qingdou-batch-v1",
  "public_text_batch_path": "copy-check-v1/public-text-batch.txt",
  "copy_guard_report_path": "copy-check-v1/public-copy-guard.json",
  "cover_validation_path": "cover-validation.json",
  "qingdou_report_path": "qingdou-report.json"
}
```

`qingdou-report.json` 必须写明 `tool=Qingdou`、`task_id`、`run_id`、`status`、`checked_at`、完整 `checked_fields`、同一 `public_text_sha256`、`batch_sha256`、`submission_mode=single_batch`、`evidence_path`、`evidence_sha256` 和 `findings`。PASS时 `findings=[]` 必须显式存在；有命中写FAIL/`risk_detected`和真实命中明细，先入库再修改。历史未带批次绑定的检测记录不自动晋级到新规则。

运行：

```bash
python3 departments/visual-design-video/scripts/validate_cover_safe_zone.py \
  delivery/creative/<task_id>/publish-cover-report.json \
  --out delivery/creative/<task_id>/cover-validation.json

python3 departments/visual-design-video/scripts/validate_douyin_publish_package.py \
  delivery/creative/<task_id>/publish-package.json
```

两个检查都 PASS、Qingdou 证据与当前公开文字哈希一致，才可以把发布文字与封面标为 `ready_for_independent_qa`。这不等于抖音审核通过，也不等于已经发布。
