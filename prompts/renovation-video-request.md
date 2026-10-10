# 六类装修视频：统一调用入口

用户统一调用 `$full-house-custom-ad`，不分别调用旧选题提示词。项目规则唯一入口是 `departments/visual-design-video/SKILL.md`；知识、文字、封面和音乐分别按其引用执行，此处只提供调用示例，不维护第二套规则。

```text
$full-house-custom-ad
做一条【类型与空间】视频，重点【具体使用需求】，直接交成片。
未指定风格时使用下一个轮换风格。描述和话题一起给我，不上传或发布。
```

| 需要的视频 | 类型与空间示例 | 项目选择器 product-type |
| --- | --- | --- |
| 设计展示 | 全屋／客厅／厨房／卧室／卫浴／阳台／理发店设计展示 | realistic_effect_ad |
| 柜体细节 | 餐边柜设计细节，展示、隐藏收纳和灯光搭配 | cabinet_detail_explainer |
| 装修避坑 | 衣柜收纳避坑，一条讲清一个具体问题 | renovation_mistake_guide |
| 方案讲解 | 全屋定制方案，整套空间合成一条 | design_plan_pitch |
| 品牌流程 | FLASH CAST已确认服务流程 | brand_process_ad（固定资料，不轮换） |
| 改造对比 | 客厅收纳与活动空间改善，同房间同视角 | concept_before_after |

指定房间就严格保持该范围；全屋使用whole_home组合。理发店等明确商用空间使用commercial范围。未指定选题用当前活动库去重选择，不能只换风格；不把未覆盖专业工程事实编成设计知识。

需要先审图时增加“先给效果图和代表帧确认，再合成”。默认直接成片仍自行做代表帧与成片检查，不把内部审图变成反复等待老板。
