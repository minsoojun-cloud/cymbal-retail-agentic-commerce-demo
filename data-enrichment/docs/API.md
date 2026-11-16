# API Contract (frontend ⇔ backend)

All responses are JSON (UTF-8). Japanese labels are provided by the backend where noted.

## Common: Record object (`rec`)
One extracted attribute or feature tag of a SKU.
```json
{
  "sku": "00081900756",
  "kind": "attribute",              // "attribute" | "tag"
  "attr_key": "net_weight_g",       // tags: "tag:骨なし・食べやすい"
  "label": "幅",                    // Japanese label (tags: tag name)
  "raw_value": "W70.0×H177.5×D68.0cm", // Gemini transcription (as written in source)
  "value": 700.0,                   // normalized value (number | string | bool | null)
  "unit": "mm",
  "norm_note": "W×H×D 表記を分解し mm に換算",
  "evidence": "W70.0×H177.5×D68.0cm", // snippet copied from source text (highlight this in source_text)
  "source_field": "attributes",     // title | description | attributes | ""
  "self_conf": 0.95,                // model self-reported
  "evidence_match": 1.0,            // 1.0 exact / 0.8 fuzzy / 0.5 raw value only / 0 not found
  "token_conf": 0.97,               // exp(avgLogprobs) or null
  "score": 0.97,                    // composite
  "gate_status": "auto_approved",   // auto_approved | needs_review | rejected | approved | edited | human_rejected
  "gate": "gate2",                  // gate1 (rules) | gate2 (score)
  "reason": "複合スコア 0.97 ≥ 0.90",
  "job_id": "live-20260930-...",
  "model": "gemini-3.8-flash",
  "created_at": "2026-09-30T02:40:00+00:00",
  "reviewed": {"action": "approve", "comment": "", "at": "..."}   // optional, only after HITL
}
```
Status display: auto_approved=🟢自動承認, approved=🟢承認済(人手), edited=🔵修正済, needs_review=🟡要レビュー, rejected=🔴棄却(ルール), human_rejected=⚫却下(人手).

## GET /api/config
```json
{"threshold":0.9,"model":"gemini-3.8-flash","batch_model":"gemini-3.8-flash",
 "groups":{"fresh":"生鮮（野菜・果物・肉・魚）","prepared":"惣菜・冷凍・主食","grocery":"加工食品・飲料","kitchen":"キッチン・調理器具","living":"日用品・生活雑貨","beauty":"ビューティー","pet":"ペット用品"},
 "feature_tags":{"fresh":["旬","国産",...],...}, "allergens_28":["えび","かに",...], "store_url":"https://cymbal-site-adk-…",
 "weights":{"evidence":0.5,"self":0.3,"token":0.2}}
```

## GET /api/dashboard
```json
{
  "totals":{"skus":100,"processed":100,"attributes":1234,"tags":456,"auto_approved":1000,"needs_review":150,"rejected":5,"human_approved":20,"human_rejected":3},
  "fill_rate":{"before":0.42,"after":0.88},
  "auto_approve_rate":0.83,
  "by_group":[{"group":"fresh","label":"生鮮（野菜・果物・肉・魚）","skus":9,"processed":9,"fill_before":0.47,"fill_after":0.69,"auto_rate":0.86,"needs_review":8,"avg_tags_after":3.2}],
  "funnel":{"source_skus":100,"extracted":1234,"normalized":1200,"gate1_passed":1190,"auto_approved":1000,"needs_review":150,"rejected":5,"golden_skus":80},
  "cost":{"basis":"batch","per_sku_jpy":0.05,"slide_per_sku_jpy":0.061,"total_jpy":5.0,"input_tokens":123456,"output_tokens":45678,"skus_measured":100},
  "recent_reviews":[{"sku":"...","attr_key":"...","action":"approve","reviewed_at":"..."}]
}
```

## GET /api/products?group=&status=&q=
`status` ∈ `completed` | `needs_review` | `not_processed`.
```json
{"items":[{"sku":"...","title":"...","brand":"...","group":"prepared","group_label":"惣菜・冷凍・主食","image_url":"https://...","price":354,
           "status":"needs_review","fill_before":0.38,"fill_after":0.92,"attr_count":14,"auto_approved":12,"needs_review":2,
           "rejected":0,"tags":["電子レンジ調理","お弁当向き"]}],
 "total":100}
```

## GET /api/products/{sku}
```json
{
  "product":{"sku":"...","title":"...","brand":"...","category":"冷凍食品・アイス > 冷凍 ごはん > ...","description":"...内容量：450g / 産地：国内製造 / 保存方法：冷凍 / 特定原材料：えび・小麦・乳","product_url":"https://cymbal-site-…/?product=...",
             "image_url":"https://...","price":354,"group":"prepared","group_label":"惣菜・冷凍・主食","raw_attributes":{"size":"450g","storage_type":"冷凍食品","allergens":"えび / 小麦 / 乳"}},
  "source_text":"【タイトル】...\n【説明文】...\n【属性】\ndimensions: W70.0×...",
  "targets":[{"key":"net_weight_g","label":"内容量（重量）","unit":"g","type":"number","raw_keys":["size"]}],
  "records":[rec, ...],
  "extras":{"search_keywords":["えびピラフ","冷凍ピラフ",...],"ai_summary":"..."},
  "gmc":{...},
  "status":"needs_review","fill_before":0.38,"fill_after":0.92
}
```
`targets` = all golden attributes for the category (show missing ones as grey "未抽出" cards).

## POST /api/products/{sku}/enrich  (live run, Server-Sent Events)
Response `Content-Type: text/event-stream`; each message `data: {json}\n\n`. Use `fetch()` + ReadableStream reader (POST).
```
{"event":"start","sku":"...","model":"gemini-3.8-flash"}
{"event":"stage","stage":"stage1","status":"running"}          // ② Gemini抽出
{"event":"stage","stage":"stage3","status":"running"}          // ② (tags) in parallel
{"event":"stage","stage":"stage1","status":"done","latency_ms":4200,"input_tokens":1500,"output_tokens":600,"count":14}
{"event":"stage","stage":"stage3","status":"done","latency_ms":3900,"count":5}
{"event":"stage","stage":"normalize","status":"done","count":14,"failed":1}   // ③ 単位正規化
{"event":"stage","stage":"gate","status":"done","summary":{"auto_approved":11,"needs_review":3,"rejected":0}} // ④
{"event":"result","detail":{...same as GET /api/products/{sku}...}}         // ⑤
{"event":"error","message":"..."}
```

## CSV Live Test Endpoints
- `GET /api/csv/sample.csv` — Download sample 3-product CSV file.
- `GET /api/csv/sample` — Returns `{"items": [...], "count": 3, "columns": [...], "csv_text": "..."}`.
- `POST /api/csv/parse` — Body: `{"csv_text": "..."}` → returns parsed products with auto-detected category `group` and `fill_before`.
- `POST /api/csv/enrich` — SSE stream (`text/event-stream`) running `gemini-3.8-flash` (Stage 1 + Stage 3 + GMC Conversational Attributes) per CSV row and saving to BigQuery (`source_products`, `enriched_attributes`, `sku_extras`, `golden_records`, `gmc_conversational`).
- `POST /api/csv/save-bq` — Body: `{"skus": ["..."]}` → explicitly persists SKUs to all 5 BigQuery tables.

## Google Merchant Center Conversational Attributes Endpoints
Reference: `https://support.google.com/merchants/answer/17085370?hl=en`
- `GET /api/gmc?group=&q=` — Returns summary KPIs (`stats`) and per-SKU GMC conversational attribute summaries (`items`).
- `GET /api/gmc/{sku}` — Returns `{"product": {...}, "source_text": "...", "gmc": {...}, "feed_row": {...}}`.
- `POST /api/gmc/{sku}/generate` — Runs `gemini-3.8-flash` to regenerate GMC conversational attributes for `{sku}` and saves to BigQuery `cymbal_enrichment.gmc_conversational`.
- `PUT /api/gmc/{sku}` — Saves human edits to `item_group_id`, `item_group_title`, `variant_options`, `questions_and_answers`, `product_highlights`, `related_products`, `popularity_rank`, and `document_link`, recomputing GMC feed strings and persisting to BigQuery.
- `GET /api/gmc/export.tsv` / `GET /api/gmc/export.csv` — Exports GMC Supplemental Feed in TSV / CSV format.

## GET /api/reviews?group=
HITL queue (records with gate_status == needs_review), most uncertain first.
```json
{"items":[{"rec":rec,"product":{"sku":"...","title":"...","image_url":"...","group_label":"生鮮（野菜・果物・肉・魚）"},"source_text":"..."}],"count":42}
```

## POST /api/reviews/{sku}/{attr_key}
Body: `{"action":"approve"|"edit"|"reject","value":<new value for edit>,"comment":"..."}` (attr_key must be URL-encoded, e.g. `tag%3A骨なし・食べやすい`). For `allergens`, edit values are validated against the 28 特定原材料 (e.g. `えび・小麦` or `なし`); approving an empty placeholder returns 400.
```json
{"record":rec,"remaining":41}
```

## GET /api/batch/jobs
```json
{"jobs":[{"job_id":"projects/.../batchPredictionJobs/123","display_name":"enrich-20260930-0240","model":"gemini-3.8-flash",
          "state":"JOB_STATE_SUCCEEDED","sku_count":100,"request_count":200,"input_tokens":150000,"output_tokens":60000,
          "cost_jpy":5.1,"created_at":"...","updated_at":"...","ingested":true}]}
```
## POST /api/batch/jobs
Body: `{"group":null|"fresh","limit":10}` → `{"job":{...}}` (submits a real Vertex AI Batch Prediction job; takes minutes).
## POST /api/batch/jobs/refresh
Polls running jobs, ingests finished ones → `{"jobs":[...]}`

## GET /api/cost/estimate?skus=200000
```json
{"skus":200000,"per_sku_jpy_measured":0.052,"per_sku_jpy_slide":0.061,"total_jpy_measured":10400,"total_jpy_slide":12200,
 "avg_input_tokens":1500,"avg_output_tokens":600,"basis":"batch (50% off)"}
```

## GET /api/golden?group=   ·   GET /api/golden/export.csv
```json
{"items":[{"sku":"...","title":"...","group":"fresh","attributes":{"net_weight_g":{"value":240,"unit":"g","score":1.0,"status":"auto_approved"}},
           "feature_tags":["骨なし・食べやすい"],"search_keywords":[...],"ai_summary":"...","fill_rate_before":0.38,"fill_rate_after":0.92,"updated_at":"..."}]}
```
