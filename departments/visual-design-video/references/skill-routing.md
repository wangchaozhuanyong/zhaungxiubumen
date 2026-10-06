# 视觉设计与视频部技能路由

老板2026-09-27要求学习六平台短视频自然增长Skill。本轮按fc-20260927-short-video-organic-skill-study-v1任务包研究、静态学习和内部应用；原4个生产子Skill继续用于制作。外部新Skill不是默认生产路由，只有准确版本/路径/范围获总控白名单及固定QA核验后再使用。后续视频创作须加载已验收学习交接，不把视频下载/上传工具当成流量方法。

## 主路线

| 任务 | 主技能 | 可按需调用 | 关键限制 |
|---|---|---|---|
| 单张广告图、封面、横幅、概念效果图、图片编辑 | `$imagegen` | 普通图像检查 | 不启动完整视频工程 |
| 装修空间、室内设计、定制柜、案例或获客视频 | `$full-house-custom-ad` | `$imagegen`、`$hyperframes`、`$media-use` | 先定 `presentation_mode`，不得自动套文案/英文模板 |
| 非装修专项的视频、动效、字幕或包装 | `$hyperframes` | `$media-use` | 跟随 HyperFrames 路由 |
| BGM、SFX、图片、图标的冻结和来源台账 | `$media-use` | 当前视频主路线 | 未授权素材不得进入公开 final |

本地 `reference_media.py` 和 `music_library.py` 只是取证/辅助脚本，不是新增子技能。

## 装修视频路由顺序

1. 先按 `adaptive-renovation-workflow.md` 建立当前 `task_id/run_id` 和六个核心产物。
2. 确定 `video_need`、`input_mode`、`presentation_mode`、`source_tier` 和 `style_profile`，不得从工具或旧模板倒推需求。
3. 有参考链接/视频时，先用本地适配器冻结并分析；完成后才交 `$full-house-custom-ad` 做原创行业转化。
4. `visual_music` 先用 `$media-use`/本地音乐目录处理具体音轨，再由 `$full-house-custom-ad` 设计空间与镜头，最后用 `$hyperframes` 组合输出。
5. `copy_led` 才调用装修 Skill 的客户心理、文字钩子、脚本、字幕和 CTA 方法。
6. 完整渲染前通过代表帧门；渲染后按每个 scene 中点与转场边界做逐镜 QC，本批次通过后才生成 handoff package。

## 强制规则

- 用户说无文案、不要字、只看空间或跟音乐走：`presentation_mode=visual_music`，`copy_mode=none`。
- “无素材”只决定真实性和生产方式，不决定必须有文案。
- “获客视频”不自动等于文案片；主片可无字，CTA 可放发布说明或独立版本。
- 用户未要求英文时，不自动生成英文装饰词。
- 参考视频未形成可播放本地正文、ffprobe 和 contact sheet 前，不得称为已分析。
- 音乐推荐、实际挂载、成片可听和发布授权必须分别验收。
- 子技能不可用、缺授权、需要付费或登录时准确记录 blocker，不静默降级成低质量 final。
- 用户只要方案时不渲染；明确说执行/制作时才生成文件。
- 没有真实素材时使用合规的 AI 概念/知识/流程路线并正确披露，不第一轮把创意任务退回给用户。

## 部门交接

- `visual_music/copy_mode=none`：内容部只复核发布说明、必要披露或渠道元数据，不补写视频内文案。
- `minimal_brand` 或 `copy_led`：公开文字交 `content-organic-website` 复核。
- 渠道、受众、历史表现和测试指标交 `paid-growth-data` 验证。
- 客户展示、报价阶段和线索反馈交 `sales`。
- 事实、版权、真实性、音乐四态和发布前检查交 `qa`。
