# 概念改造视频选题器

1. 读取 `data/knowledge/full-house-custom-knowledge-manifest.json`。
2. 用知识轮换脚本 `peek --product-type concept_before_after` 取得下一条 `topic_id + style_id + variant_id`。
3. Before 与 After 固定同机位、同焦段、同空间边界和主要开口；不能靠换房间制造假对比。
4. 每支至少改变 2 个独立维度：动线、功能、收纳、比例、灯光、材质、隐私或维护。
5. 必须标注 `概念改造演示 / 方案对比`，右下角视觉标签使用用户指定的 `仅设计效果图`；不得冒充实际施工前后。
6. 只有方案或成片被实际采用后才运行 `commit`，候选不登记。

默认去重：最近 32 支不重复同一条，最近 4 支不重复同一分类。
