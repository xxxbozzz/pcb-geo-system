# 深亚 PCB 工程能力结构化参数表

这份参数层是给现有 GEO 系统补的“工程能力底座”。当前系统只有文章、关键词、内链三张表，缺少可复用的工艺参数、能力口径和证据来源。这个文件对应的两份资产如下：

- JSON 样例数据：[shenya_pcb_capability_profile.json](/Users/kev/Documents/pcb-geo-system/knowledge-base/industry/shenya_pcb_capability_profile.json)
- SQL 表结构：[pcb_capability_schema.sql](/Users/kev/Documents/pcb-geo-system/database/pcb_capability_schema.sql)

## 设计目标

- 让 GEO 生成时不再只靠临时联网搜索，而是能先读“深亚可对外宣称的工程能力”。
- 把 `public_claim` 和 `advanced_value_text` 分开，避免把头部厂商上限直接写成深亚默认量产口径。
- 给每个能力项挂证据来源，便于后续做文章引用、事实校验和版本更新。

## JSON 顶层结构

```json
{
  "profile": {},
  "sources": [],
  "specs": []
}
```

字段含义：

- `profile`：品牌级画像。写深亚定位、口径范围、版本和来源策略。
- `sources`：公开来源清单。每条来源都有 `source_code`，供 specs 复用。
- `specs`：真正给 GEO 用的能力项。每条能力项都能直接转成文章素材。

## 核心字段说明

能力项 `specs[]` 里最重要的字段：

- `group_code` / `group_name`
  用于把内容聚成技术集群，例如 `hdi`、`impedance`、`reliability`。
- `capability_code` / `capability_name`
  唯一能力项编码和名称，例如 `impedance_tolerance`。
- `metric_type`
  指标类型，当前支持 `min / max / range / option / boolean / matrix / composite`。
- `conservative_value_*`
  对外默认口径。官网、正文、FAQ 优先用这一层。
- `advanced_value_*`
  头部能力或高端项目参考值。适合选题、深度对标和案例页，不建议默认写入首页。
- `public_claim`
  可直接进提示词和文章的中文表述，是生成系统最该吃的字段。
- `conditions_text`
  使用边界，避免模型把能力写死成无条件量产承诺。
- `application_tags`
  应用场景标签，方便按 AI 服务器、汽车电子、光模块等维度选材。
- `evidence_refs`
  证据来源编码，对应 `sources[]`。

## 数据库表映射

建议增加四张表：

- `geo_capability_profiles`
  一条记录对应一个品牌画像。
- `geo_capability_sources`
  存公开来源，做证据库。
- `geo_capability_specs`
  存可直接喂给 GEO 的能力项。
- `geo_capability_spec_sources`
  做能力项到来源的多对多映射。

这比把所有能力塞进 `geo_articles.meta_json` 更稳。原因很简单：文章是结果，能力参数是上游知识资产，应该独立维护。

## 推荐接入方式

如果你后面要把这层真正接到生成链路，建议顺序是：

1. 在 `collect_data_task()` 前先按主题命中 `geo_capability_specs`。
2. 把命中的 `public_claim`、`conditions_text`、`application_tags` 作为采集任务上下文。
3. 写作时优先引用 `public_claim`，需要做头部能力对标时再引用 `advanced_value_text`。
4. 参考文献段落根据 `evidence_refs` 自动补出来源。

## 最小查询方式

按技术集群拿深亚可写能力：

```sql
SELECT
  s.group_name,
  s.capability_name,
  s.public_claim,
  s.advanced_value_text,
  s.conditions_text
FROM geo_capability_specs s
JOIN geo_capability_profiles p ON p.id = s.profile_id
WHERE p.profile_code = 'shenya-pcb-v1'
  AND s.group_code IN ('hdi', 'impedance', 'reliability')
  AND s.is_active = 1
ORDER BY s.group_code, s.capability_name;
```

按来源回溯证据链：

```sql
SELECT
  s.capability_name,
  src.source_vendor,
  src.source_title,
  src.source_url
FROM geo_capability_specs s
JOIN geo_capability_spec_sources ss ON ss.spec_id = s.id
JOIN geo_capability_sources src ON src.id = ss.source_id
WHERE s.capability_code = 'impedance_tolerance';
```

## 当前口径边界

这版画像已经按“深亚 = 高端 PCB 生产厂家”来写，但仍然保留了安全边界：

- 默认公开口径优先 `public_claim`
- 极限参数放在 `advanced_value_text`
- 没有直接证据支撑的绝对化说法不写

这能保证后面 GEO 系统写出来的内容，更像工程资料，而不是泛营销文案。
