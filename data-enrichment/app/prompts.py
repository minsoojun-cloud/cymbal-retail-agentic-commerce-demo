"""Prompts for multi-stage extraction (Stage 1), classification (Stage 3) and GMC conversational attributes."""
from __future__ import annotations

from .schema import ALLERGENS_28, CATEGORY_GROUPS, attrs_for_group

RETAILER = "食品スーパー兼総合EC「Cymbal Retail」"


def source_text(p: dict) -> str:
    """Canonical source text used both for prompting and for evidence verification."""
    lines = [f"【タイトル】{p.get('title', '')}", f"【ブランド】{p.get('brand', '')}",
             f"【カテゴリ】{p.get('category', '')}", f"【説明文】{p.get('description', '')}", "【属性】"]
    for k, v in (p.get("raw_attributes") or {}).items():
        lines.append(f"{k}: {v}")
    docs = p.get("doc_sources") or []
    if docs:
        lines.append("【資料】")
        for d in docs:
            where = f"{d.get('file_name', '')}" + (f" p.{d['page']}" if d.get("page") else "")
            lines.append(f"[{where}] {d.get('label') or d.get('key', '')}: {d.get('evidence') or d.get('value', '')}")
    return "\n".join(lines)


def stage1_prompt(p: dict, group: str) -> str:
    defs = "\n".join(f"- {a.key}: {a.label}" + (f"（最終単位 {a.unit}）" if a.unit else "") + (f" … {a.hint}" if a.hint else "")
                     for a in attrs_for_group(group))
    return f"""あなたは{RETAILER}の商品マスタ整備担当です。
以下の原本データ（{CATEGORY_GROUPS[group]}）から、指定された属性を抽出してください。

## 厳守ルール
1. raw_value には原文に書かれている値を「単位込みでそのまま」転記すること。単位換算・計算・丸めは絶対にしない（換算は後段のシステムが行う）。
   例: 原文「内容量：3切（約240g）」→ net_weight_g の raw_value は「3切（約240g）」、pack_count も「3切（約240g）」
   例: 原文「幅45×奥行45×高さ40cm」→ width_cm / depth_cm / height_cm の raw_value はいずれも「幅45×奥行45×高さ40cm」
2. evidence には根拠となる原文の連続した文字列を一字一句そのままコピーすること（要約・言い換え禁止、40字以内）。
3. 原文に記載がない属性は推測で埋めず、not_found に入れること（ハルシネーション防止）。
4. 一般常識からの推定（例: 「えびフライだから特定原材料はえび」「鍋だからIH対応」）は、原文に明確な記述がない限り行わない。
5. **allergens（特定原材料）は食品安全上もっとも重要**。「特定原材料：」「アレルゲン」「アレルギー表示」など明示的な表示がある場合のみ、
   その表示を raw_value にそのまま転記する（例:「特定原材料：えび・小麦・卵・乳」）。表示がなければ必ず not_found に入れる。
   対象は28品目（{'・'.join(ALLERGENS_28)}）。
6. 構造化属性（【属性】の key: value）に値がある場合、source_field は attributes、evidence は「key: value」の形で転記する。
7. confidence は原文の記述の明確さに応じて 0.0〜1.0 で自己評価すること。

## 抽出対象の属性
{defs}

## 原本データ
{source_text(p)}
"""


def stage3_prompt(p: dict, group: str) -> str:
    return f"""あなたは{RETAILER}のECサイト編集者です。
以下の原本データ（{CATEGORY_GROUPS[group]}）を読み、検索・絞り込みに使う標準機能タグと検索キーワード、要約を作成してください。

## 厳守ルール
1. feature_tags は指定の標準タグ辞書（enum）からのみ選ぶこと。原文に根拠がないタグは付けない。
2. 各タグの evidence には根拠となる原文の文字列を一字一句そのままコピーすること（40字以内）。
3. 言い回しの違う表現（例:「骨がなく子どもにも食べやすい」→ 骨なし・食べやすい、「焼くだけ」→ 時短）は意味の近い標準タグに対応付けること。
4. 「旬」タグは原文に旬・時期の記載（labels の 旬、season_months など）がある場合のみ。
5. ai_summary は原文の事実のみで60〜90字にまとめること。アレルゲンや健康効果など原文にない事実は書かない。

## 原本データ
{source_text(p)}
"""


def gmc_prompt(p: dict, group: str) -> str:
    return f"""あなたは Google Merchant Center（GMC）の会話属性（Conversational Attributes: https://support.google.com/merchants/answer/17085370）の構築スペシャリストです。
以下の{RETAILER}の取扱商品の原本データ（{CATEGORY_GROUPS.get(group, group)}）から、AI検索（Google 検索の AI モード等）や会話型ショッピングエージェントが顧客の質問に正確に答えられるよう、日本語で会話属性データを作成してください。

## 厳守ルール
1. **item_group_id / item_group_title**:
   - 原本属性 base_id があればそれを item_group_id にそのまま使う。なければ内容量・入数・色を除いた商品名の共通部分から短いIDを作る。
   - 内容量・入数・サイズ・色などを除いたシリーズ共通のわかりやすい名称を item_group_title とする（例:「Cymbal 白玉子」）。
2. **variant_options [variant_option]**:
   - この商品を同じグループ内で識別するプロパティ（内容量、入数、サイズ、味・辛さ、カラー、産地など）を 2〜4 個、根拠 evidence 付きで抽出する。
3. **questions_and_answers [question_and_answer]**:
   - 購入検討者が実際に尋ねそうな具体的な質問と回答を **3〜5件** 作成する
     （食品の例: 内容量・何人分か、保存方法、調理方法・調理時間、産地、特定原材料（アレルギー）、おすすめの食べ方。
       日用品・雑貨の例: サイズ、素材、IH・食洗機・電子レンジ対応、対象ペット・年齢、香り、お手入れ）。
   - **回答は必ず原本データの事実のみに基づくこと（推測・ハルシネーション厳禁）**。
   - アレルギーに関する質問は、原文に特定原材料の表示がある場合のみ作成し、表示どおりに答える。表示がない場合はアレルギーの質問を作らない。
   - 各回答の根拠となる原文の連続文字列を evidence に一字一句そのままコピーすること（40字以内）。
4. **product_highlights [product_highlight]**:
   - 商品の主要セールスポイントを簡潔な箇条書き（3〜5件、各40字以内）でまとめる。
5. **related_mentions [related_product]**:
   - 説明文中に「〜と一緒に」「〜にも合う」など明示された関連商品・別売品があれば抽出する（なければ空配列 `[]`）。
6. **document_link**: 原文に URL があれば記載、なければ空文字（作らない）。

## 原本データ
{source_text(p)}
"""
