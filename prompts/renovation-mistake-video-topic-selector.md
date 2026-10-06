# 装修避坑视频选题调用规则

数据源：`data/knowledge/renovation-mistake-knowledge-base-v1.json`  
使用记录：`data/knowledge/renovation-mistake-used-topics.json`

## 调用流程

1. 先读取知识库和使用记录。
2. 默认从最近 30 支视频未使用的条目中选择。
3. 最近 3 支视频避免重复同一分类；用户明确指定分类时除外。
4. 一支 12–30 秒视频只讲 1 个主避坑点；最多带 1 个相关补充点。
5. 结构固定为：具体场景钩子 → 错误做法 → 后果 → 正确动作 → 一句记忆点。
6. 画面必须对应知识点，不能用与主题无关的豪宅图填充。
7. `high` 或 `critical` 风险主题在制作前重新打开对应官方来源核对；涉及结构、电气、防火、审批时，不给项目级结论，明确要求合资格专业人士或主管部门确认。
8. 成片使用 AI 概念画面时，右下角统一显示：`仅设计效果图`。
9. 视频实际完成后，把 `topic_id`、`task_id`、日期和标题追加到使用记录。

## 选题输出格式

- `topic_id`
- `category`
- `target_viewer`
- `hook`
- `mistake`
- `consequence`
- `correct_action`
- `memory_line`
- `visual_plan`
- `source_ids`
- `risk_boundary`

不得为了刺激点击把一般建议写成绝对法规，也不得使用“百分百”“一定不会”“永久解决”等结果承诺。
