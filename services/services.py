# -*- coding: utf-8 -*-
# services.py
import os
from typing import Dict, List
import copy # copyモジュールを追加
import uuid
import json

from structure_templates import STRUCTURE_TEMPLATES

# =========================
# Load Default Composition Meta from JSON
# =========================
def _load_composition_meta():
    """Loads the composition meta from an external JSON file."""
    # Construct path relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Assuming services.py is in services/ and the json is in the root
    meta_path = os.path.join(base_dir, '..', 'composition_meta.json') 
    with open(meta_path, 'r', encoding='utf-8') as f:
        return json.load(f)

DEFAULT_COMPOSITION_META = _load_composition_meta()

# =========================
# Document Service
# =========================

def create_document(
    data: Dict,
    title: str,
    doc_type: str
) -> Dict:
    """
    新しい Document を作成し、data["documents"] に追加する。
    data は load_user_data() で取得した dict を想定。
    """

    document = {
        "id": os.urandom(4).hex(),
        "title": title,
        "doc_type": doc_type,
        "intent": {},
        "units": [
            {"title": t, "content": ""}
            for t in STRUCTURE_TEMPLATES[doc_type]
        ],
        "entities": [],
        "composition_elements": {}, # 新しい構成要素の格納場所
        "composition_meta": copy.deepcopy(DEFAULT_COMPOSITION_META) # デフォルトのメタ定義を追加
    }

    data.setdefault("documents", []).append(document)
    return document


# =========================
# Composition Elements Service
# =========================

def _get_default_element_instance(element_meta: dict) -> dict:
    """要素のメタ情報に基づいてデフォルトの要素インスタンスを生成する"""
    return {
        "id": element_meta["id"],
        "label": element_meta["label"],
        "value": ""
    }


def _get_default_element_instance_for_new_category() -> dict:
    return {
        "id": str(uuid.uuid4().hex[:8]),
        "label": "新しい項目",
        "value": "",
        "editable": True
    }

def _normalize_categories(current_categories: list, meta_categories: list):
    """カテゴリとその要素をメタ定義に基づいて初期化・正規化するヘルパー関数"""

    # メタ定義にないカテゴリを削除（古いデータをクリーンアップ）
    # ただし、ユーザーが追加した編集可能なカテゴリは残す
    meta_category_ids = {cat["id"] for cat in meta_categories}
    current_categories[:] = [
        cat for cat in current_categories if cat["id"] in meta_category_ids or cat.get("editable")
    ]


    for category_meta in meta_categories:
        category_id = category_meta["id"]
        category_found = False

        for existing_category in current_categories:
            if existing_category["id"] == category_id:
                # カテゴリが見つかったら、そのメタ情報を更新し、中の要素を正規化
                existing_category["label"] = category_meta["label"]
                existing_category["editable"] = category_meta.get("editable", False)

                existing_elements = existing_category.setdefault("elements", [])

                # メタ定義にない要素を削除（ただし、ユーザーが追加した編集可能なものは残す）
                if 'elements' in category_meta:
                    meta_element_ids = {elem["id"] for elem in category_meta.get("elements", [])}
                    existing_category["elements"][:] = [
                        elem for elem in existing_elements if elem["id"] in meta_element_ids or elem.get("editable")
                    ]

                # メタ定義に基づいて不足している要素を追加 (idで比較)
                for element_meta in category_meta.get("elements", []):
                    element_found = False
                    for existing_element in existing_elements:
                        if existing_element["id"] == element_meta["id"]:
                            element_found = True
                            existing_element["label"] = element_meta["label"] # labelも更新される可能性があるのでここで上書き
                            existing_element.setdefault("value", "") # valueがなければ追加
                            break
                    if not element_found:
                        existing_elements.append(_get_default_element_instance(element_meta))

                category_found = True
                break

        if not category_found:
            # カテゴリが見つからなかった場合、メタ定義から追加
            new_category = {
                "id": category_meta["id"],
                "label": category_meta["label"],
                "editable": category_meta.get("editable", False),
                "elements": []
            }
            for element_meta in category_meta.get("elements", []):
                new_category["elements"].append(_get_default_element_instance(element_meta))
            current_categories.append(new_category)


def normalize_composition_elements(document: dict) -> None:
    """
document["composition_elements"] を初期化・正規化する
    """
    # composition_elements がなければ初期化
    if "composition_elements" not in document:
        document["composition_elements"] = {
            "common": {"categories": []},
            "doc_type_specific": {"categories": []}
        }

    # composition_meta がなければデフォルトをコピー
    if "composition_meta" not in document:
        document["composition_meta"] = copy.deepcopy(DEFAULT_COMPOSITION_META)

    elements_data = document["composition_elements"]
    composition_meta = document["composition_meta"]

    # 共通構成要素の正規化
    common_meta_def = composition_meta["common_categories"]
    _normalize_categories(
        elements_data.setdefault("common", {"categories": []}).setdefault("categories", []),
        common_meta_def["categories"]
    )

    # doc_type 固有構成要素の正規化
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in composition_meta["doc_types"].items()}
    mapped_doc_type = doc_type_mapping.get(document["doc_type"])

    if mapped_doc_type:
        doc_type_meta_def = composition_meta["doc_types"].get(mapped_doc_type)
        if doc_type_meta_def and "categories" in doc_type_meta_def:
            _normalize_categories(
                elements_data.setdefault("doc_type_specific", {"categories": []}).setdefault("categories", []),
                doc_type_meta_def["categories"]
            )


def update_composition_elements(document: dict, form_data) -> None:
    """
    Composition Elements を更新・追加・削除する (v2)
    """
    # normalize_composition_elements はすでに app.py のGETリクエスト時に呼ばれている前提
    elements_data = document["composition_elements"]
    composition_meta = document["composition_meta"] # documentからcomposition_metaを取得

    # 日本語の doc_type を英語のキーにマッピング
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in composition_meta["doc_types"].items()}
    mapped_doc_type = doc_type_mapping.get(document["doc_type"])

    # --- 共通構成要素の処理 ---
    common_categories = elements_data["common"].setdefault("categories", [])
    common_meta_def = composition_meta["common_categories"] # メタ定義もcomposition_metaから取得

    # --- 共通カテゴリ自体を追加・削除する処理 ---
    if common_meta_def.get("editable", False):
        # カテゴリ追加
        if "add_common_category" in form_data:
            new_label = form_data.get("new_common_category_label", "").strip()
            if new_label:
                new_category_id = str(uuid.uuid4().hex[:8])
                new_category = {
                    "id": new_category_id,
                    "label": new_label,
                    "editable": True,
                                    "elements": []
                                }
                common_categories.append(new_category)
        # カテゴリ削除
        remove_category_id = form_data.get("remove_common_category")
        if remove_category_id:
            elements_data["common"]["categories"][:] = [
                cat for cat in common_categories if cat["id"] != remove_category_id
            ]

    # 共通カテゴリ内の要素の追加・削除・更新
    for current_category_data in common_categories: # データ内のカテゴリをループ
        category_id = current_category_data["id"]

        # カテゴリ自体のラベル更新
        category_label_from_form = f"category_{category_id}_label"
        if category_label_from_form in form_data:
            current_category_data["label"] = form_data.get(category_label_from_form, "")

        elements = current_category_data.setdefault("elements", [])

        # --- 要素の追加 ---
        if f"add_element_{category_id}" in form_data:
            # multiple はカテゴリのeditableに統合されたので、常に新しい要素を追加
            new_element = {
                "id": str(uuid.uuid4().hex[:8]), # 一時的なユニークID
                "label": "新しい項目", # デフォルトラベル
                "value": "",
                "editable": True
            }
            elements.append(new_element)

        # --- 要素の削除 ---
        remove_index_str = form_data.get(f"remove_element_{category_id}")
        if remove_index_str:
            remove_index = int(remove_index_str)
            # 項目をeditableに関わらず削除可能にする
            if 0 <= remove_index < len(elements):
                elements.pop(remove_index)

        # --- 要素の更新 ---
        for i, element in enumerate(elements):
            # valueの更新
            form_value_name = f"element_{category_id}_{i}_value"
            if form_value_name in form_data:
                element["value"] = form_data.get(form_value_name, "")

            # labelの更新
            form_label_name = f"element_{category_id}_{i}_label"
            if form_label_name in form_data:
                element["label"] = form_data.get(form_label_name, "")

    # --- doc_type 固有構成要素の処理 ---
    doc_type_specific_categories = elements_data["doc_type_specific"].setdefault("categories", [])
    doc_type_meta_def = composition_meta["doc_types"].get(mapped_doc_type) # メタ定義もcomposition_metaから取得

    if doc_type_meta_def:
        # doc_type 固有カテゴリの追加・削除 (doc_type自体がeditableな場合)
        if doc_type_meta_def.get("editable", False):
            # --- カテゴリ自体を追加する処理 ---
            if "add_doc_type_category" in form_data:
                new_label = form_data.get("new_doc_type_category_label", "").strip()
                if new_label:
                    new_category_id = str(uuid.uuid4().hex[:8])
                    new_category = {
                        "id": new_category_id,
                        "label": new_label,
                        "editable": True,
                        "elements": []
                    }
                    doc_type_specific_categories.append(new_category)

            # --- カテゴリ自体を削除する処理 ---
            remove_category_id = form_data.get("remove_doc_type_category")
            if remove_category_id:
                elements_data["doc_type_specific"]["categories"][:] = [
                    cat for cat in doc_type_specific_categories if cat["id"] != remove_category_id
                ]

        # doc_type 固有カテゴリ内の要素の追加・削除・更新
        for current_category_data in doc_type_specific_categories: # データ内のカテゴリをループ
            category_id = current_category_data["id"]

            # カテゴリ自体のラベル更新 (editableなもののみ)
            category_label_from_form = f"category_{category_id}_label"
            if category_label_from_form in form_data and current_category_data.get("editable", False):
                current_category_data["label"] = form_data.get(category_label_from_form, "")

            elements = current_category_data.setdefault("elements", [])

            # --- 要素の追加 ---
            if f"add_element_{category_id}" in form_data:
                new_element = {
                    "id": str(uuid.uuid4().hex[:8]),
                    "label": "新しい項目",
                    "value": "",
                    "editable": True
                }
                elements.append(new_element)

            # --- 要素の削除 ---
            remove_index_str = form_data.get(f"remove_element_{category_id}")
            if remove_index_str:
                remove_index = int(remove_index_str)
                # 項目をeditableに関わらず削除可能にする
                if 0 <= remove_index < len(elements):
                    elements.pop(remove_index)

            # --- 要素の更新 ---
            for i, element in enumerate(elements):
                form_value_name = f"element_{category_id}_{i}_value"
                if form_value_name in form_data:
                    element["value"] = form_data.get(form_value_name, "")

                form_label_name = f"element_{category_id}_{i}_label"
                if form_label_name in form_data:
                    element["label"] = form_data.get(form_label_name, "")


# =========================
# Unit Service
# =========================

def update_units_content(document: Dict, form_data) -> None:
    """
    POSTされたフォームから unit content を更新する
    """
    for i, unit in enumerate(document.get("units", [])):
        unit["content"] = form_data.get(f"unit_{i}", "")


# =========================
# Query Utilities
# =========================

def find_document(data: Dict, doc_id: str) -> Dict | None:
    """
    data["documents"] から document を検索
    """
    return next(
        (d for d in data.get("documents", []) if d["id"] == doc_id),
        None
    )


def update_intent(document: dict, form_data) -> None:
    """
    Intent（作者の意図）を更新・追加・削除する
    """

    intent = document.get("intent")
    # ---- ここが重要 ----
    if not intent:
        intent = {"fields": {}}

    # list → dict 変換（過去データ救済）
    if isinstance(intent.get("fields"), list):
        intent["fields"] = {
            f.get("key", f"intent_{i}"): {
                "label": f.get("label", ""),
                "value": f.get("value", "")
            }
            for i, f in enumerate(intent["fields"])
        }

    fields = intent["fields"]


    # -------------------------
    # Intent削除
    # -------------------------
    remove_key = form_data.get("remove_intent")
    if remove_key:
        fields.pop(remove_key, None)
        document["intent"] = intent
        return

    # -------------------------
    # Intent追加
    # -------------------------
    if "add_intent" in form_data:
        label = form_data.get("new_intent_label", "").strip()
        value = form_data.get("new_intent_value", "").strip()

        if label:
            key = f"intent_{uuid.uuid4().hex[:8]}"
            fields[key] = {
                "label": label,
                "value": value
            }

        document["intent"] = intent
        return

    # -------------------------
    # Intent保存（通常更新）
    # -------------------------
    for key in fields:
        value_key = f"intent_value_{key}"
        if value_key in form_data:
            fields[key]["value"] = form_data.get(value_key, "")

    document["intent"] = intent


from domain_mapper import json_to_intent
from optimizer import optimize_unit_order


def optimize_document_units(document: dict) -> None:
    """
    Document 内の Unit 配列を Intent に基づいて最適化する
    （破壊的に並び替える）
    """
    intent = json_to_intent(document.get("intent"))

    units = document.get("units", [])
    if not units:
        return

    optimized_units = optimize_unit_order(intent, units)
    document["units"] = optimized_units


from services.scoring import score_intent_unit_alignment
from connection_scoring import score_unit_connection


def attach_unit_scores(document: dict) -> None:
    """
    各 Unit にスコア情報を付与する（UI表示用）
    """
    intent = json_to_intent(document.get("intent"))
    units = document.get("units", [])

    for i, unit in enumerate(units):
        # Intent × Unit
        intent_score = score_intent_unit_alignment(
            intent,
            unit.get("content", "")
        )

        # Unit × Unit（前後）
        prev_score = None
        next_score = None

        if i > 0:
            prev_score = score_unit_connection(
                units[i - 1].get("content", ""),
                unit.get("content", "")
            )

        if i < len(units) - 1:
            next_score = score_unit_connection(
                unit.get("content", ""),
                units[i + 1].get("content", "")
            )

        unit["_score"] = {
            "intent": intent_score,
            "prev": prev_score,
            "next": next_score
        }

# =========================
# ④ スコア関連
# =========================
def score_to_color(score: float | None) -> str:
    if score is None:
        return "black"
    if score < 0.3:
        return "red"
    if score < 0.6:
        return "orange"
    return "green"

# =========================
# 赤 Unit 抽出
# =========================

def extract_red_units(document: dict) -> list[tuple[int, dict]]:
    """
    intent スコアが低い Unit を抽出
    戻り値: [(index, unit_dict), ...] 
    """
    result = []
    for i, unit in enumerate(document.get("units", [])):
        score = unit.get("_score", {}).get("intent")
        if score is not None and score < 0.3:
            result.append((i, unit))
    return result


# =========================
# LLM 用 prompt 生成
# =========================

def build_llm_prompt(document: dict, unit: dict) -> str:
    intent = document.get("intent", {})

    prompt = f"""
あなたは物語構成の編集者です。
以下の「作者の意図」と「シーン」を踏まえ、
このシーンを改善してください。

【作者の意図】
ジャンル: {intent.get('genre', '')}
テーマ・主張: {intent.get('theme_or_claim', '')}
価値観・肯定するもの: {intent.get('core_values', '')}
制約条件:
"""

    for c in intent.get("constraints", []):
        prompt += f"- {c}\n"

    prompt += f"""
【対象シーン】
タイトル: {unit.get('title', '')}
内容:
{unit.get('content', '')}

【改善指示】
- 作者の意図と整合するように修正する
- 具体性を高める
- 物語上の役割を明確にする

【改善後のシーン本文のみを出力してください】
"""

    return prompt.strip()

def normalize_intent(document: dict) -> None:
    """
    Intent を必ず
    document["intent"]["fields"] = dict
    の形に正規化する
    """
    intent = document.get("intent")

    # intent 自体が無い
    if not intent:
        document["intent"] = {"fields": {}}
        return

    # fields が無い（最初期JSON）
    if "fields" not in intent:
        fields = {}
        for k, v in intent.items():
            if k == "fields":
                continue
            fields[k] = {
                "label": k,
                "value": v if not isinstance(v, list) else "\n".join(v)
            }
        document["intent"] = {"fields": fields}
        return

        

        # fields が list（中期JSON）

        if isinstance(intent.get("fields"), list):

            intent["fields"] = {

                f.get("key", f"intent_{i}"): {

                    "label": f.get("label", ""),

                    "value": f.get("value", "")

                }

                for i, f in enumerate(intent["fields"])

            }

    

def build_composition_ideas_prompt(document: dict) -> str:

    """
    LLMに構成要素のアイデアを生成させるためのプロンプトを構築する。
    """

    intent_fields = document.get("intent", {}).get("fields", {})

    intent_text = "\n".join(f"- {data['label']}: {data['value']}" for key, data in intent_fields.items() if data.get('value'))

    

    composition_elements = document.get("composition_elements", {})

    elements_text = ""

    for scope in ["common", "doc_type_specific"]:

        for category in composition_elements.get(scope, {}).get("categories", []):

            category_label = category.get("label")

            elements_text += f"\n▼{category_label}\n"

            for element in category.get("elements", []):

                if element.get("value"):

                    elements_text += f"- {element['label']}: {element['value']}\n"

    

    prompt = f"""
あなたはプロの作家・編集者です。

以下の作品のコンテキストを読み、この作品をより面白くするための新しい構成要素のアイデアを5つ提案してください。

提案は具体的で、既存の要素と組み合わせることで物語や論理が深まるようなものにしてください。

# 作品コンテキスト

## 基本情報

- タイトル: {document.get("title", "（無題）")}

- 種類: {document.get("doc_type", "（未設定）")}

## 作者の意図

{intent_text if intent_text else "（未設定）"}

## 現在の構成要素

{elements_text if elements_text.strip() else "（まだ構成要素はありません）"}

# あなたへの指示

- 上記コンテキストに合致し、かつ新規性のあるアイデアを5つ、簡潔な日本語で提案してください。

- 応答は必ず以下のJSON形式のみで出力してください。他のテキストは一切含めないでください。

```json
{{
  "suggestions": [
    "提案1",
    "提案2",
    "提案3",
    "提案4",
    "提案5"
  ]
}}
```

"""

    return prompt.strip()
