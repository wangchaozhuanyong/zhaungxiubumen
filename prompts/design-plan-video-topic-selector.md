# 设计方案讲解片选题器

1. 读取 `data/knowledge/full-house-custom-knowledge-manifest.json`。
2. 用知识轮换脚本 `peek --product-type design_plan_pitch` 取得下一条 `topic_id + style_id + variant_id`。
3. 围绕 1 个主命题讲清：客户问题、设计判断、空间/柜体/材质/灯光证据、适用边界。
4. 画面至少出现一种可验证表达：动线图、柜体剖面、轴线、材质板、开门包络、灯光层级。
5. 明确标注 `概念方案演示`，右下角视觉标签使用用户指定的 `仅设计效果图`；不得说成真实客户交付。
6. 只有方案或成片被实际采用后才运行 `commit`，候选不登记。

默认去重：最近 40 支不重复同一条，最近 4 支不重复同一分类。
