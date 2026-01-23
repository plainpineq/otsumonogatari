# services.py
import os
from typing import Dict, List

from structure_templates import STRUCTURE_TEMPLATES, COMPOSITION_ELEMENTS_META
import uuid


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
        "composition_elements": {} # 新しい構成要素の格納場所
    }

    data.setdefault("documents", []).append(document)
    return document


# =========================
# Composition Elements Service
# =========================

def _get_default_element_instance(category_meta: dict) -> dict:
    """カテゴリのメタ情報に基づいてデフォルトの要素インスタンスを生成する"""
    if "instance_structure" in category_meta:
        instance = {}
        for field_id, field_meta in category_meta["instance_structure"].items():
            print(f"DEBUG (get_default): field_id={field_id}, field_meta={field_meta}, field_meta.get('values')={field_meta.get('values')}") # 追加
            if field_meta["type"] == "text":
                instance[field_id] = ""
            elif field_meta["type"] == "enum" and field_meta["values"]:
                instance[field_id] = field_meta["values"][0] # 最初のenum値をデフォルトとする
            else:
                instance[field_id] = ""
        return instance
    else:
        # instance_structure がない場合は単一のテキストフィールドとして扱う
        return {"value": ""}


def normalize_composition_elements(document: dict) -> None:
    """
    Document の composition_elements を初期化・正規化する
    """
    composition_elements = document.setdefault("composition_elements", {
        "common": {},
        "doc_type_specific": {}
    })

    # 共通構成要素の正規化
    for category_meta in COMPOSITION_ELEMENTS_META["common_categories"]:
        category_id = category_meta["id"]
        if category_meta["multiple"]:
            composition_elements["common"].setdefault(category_id, [])
            if not composition_elements["common"][category_id]: # リストが空なら初期要素を追加
                 composition_elements["common"][category_id].append(_get_default_element_instance(category_meta))
        else:
            if category_id not in composition_elements["common"]:
                composition_elements["common"][category_id] = _get_default_element_instance(category_meta)

    # doc_type 固有の構成要素の正規化
    # 日本語の doc_type を英語のキーにマッピング
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in COMPOSITION_ELEMENTS_META["doc_types"].items()}
    mapped_doc_type = doc_type_mapping.get(document["doc_type"])
    
    doc_type_meta = COMPOSITION_ELEMENTS_META["doc_types"].get(mapped_doc_type)
    if doc_type_meta and "categories" in doc_type_meta:
        for category_meta in doc_type_meta["categories"]:
            category_id = category_meta["id"]
            if category_meta["multiple"]:
                composition_elements["doc_type_specific"].setdefault(category_id, [])
                if not composition_elements["doc_type_specific"][category_id]: # リストが空なら初期要素を追加
                    composition_elements["doc_type_specific"][category_id].append(_get_default_element_instance(category_meta))
            else:
                if category_id not in composition_elements["doc_type_specific"]:
                    composition_elements["doc_type_specific"][category_id] = _get_default_element_instance(category_meta)


def update_composition_elements(document: dict, form_data) -> None:
    """
    Composition Elements を更新・追加・削除する
    """
    normalize_composition_elements(document) # まず正規化しておく

    elements_data = document["composition_elements"]

    # --- 共通構成要素の処理 ---
    for category_meta in COMPOSITION_ELEMENTS_META["common_categories"]:
        category_id = category_meta["id"]
        is_multiple = category_meta["multiple"]

        # 追加
        if f"add_element_{category_id}" in form_data:
            new_instance = _get_default_element_instance(category_meta)
            if is_multiple:
                elements_data["common"].setdefault(category_id, []).append(new_instance)
            else:
                elements_data["common"][category_id] = new_instance
            continue # 他の処理はスキップして次のカテゴリへ

        # 削除
        remove_index_str = form_data.get(f"remove_element_{category_id}")
        if remove_index_str and is_multiple:
            remove_index = int(remove_index_str)
            if category_id in elements_data["common"] and len(elements_data["common"][category_id]) > remove_index:
                elements_data["common"][category_id].pop(remove_index)
            continue # 他の処理はスキップして次のカテゴリへ

        # 保存（更新）
        if is_multiple:
            if category_id in elements_data["common"]:
                for i, instance in enumerate(elements_data["common"][category_id]):
                    for field_id in instance: # instance_structure のフィールドを更新
                        form_field_name = f"element_{category_id}_{i}_{field_id}"
                        if form_field_name in form_data:
                            instance[field_id] = form_data.get(form_field_name, "")
        else: # multipleでない場合
            instance = elements_data["common"].get(category_id)
            if instance:
                for field_id in instance:
                    form_field_name = f"element_{category_id}_{field_id}"
                    if form_field_name in form_data:
                        instance[field_id] = form_data.get(form_field_name, "")


    # --- doc_type 固有構成要素の処理 ---
    doc_type_meta = COMPOSITION_ELEMENTS_META["doc_types"].get(document["doc_type"])
    if doc_type_meta and "categories" in doc_type_meta:
        for category_meta in doc_type_meta["categories"]:
            category_id = category_meta["id"]
            is_multiple = category_meta["multiple"]

            # 追加
            if f"add_element_{category_id}" in form_data:
                new_instance = _get_default_element_instance(category_meta)
                if is_multiple:
                    elements_data["doc_type_specific"].setdefault(category_id, []).append(new_instance)
                else:
                    elements_data["doc_type_specific"][category_id] = new_instance
                continue

            # 削除
            remove_index_str = form_data.get(f"remove_element_{category_id}")
            if remove_index_str and is_multiple:
                remove_index = int(remove_index_str)
                if category_id in elements_data["doc_type_specific"] and len(elements_data["doc_type_specific"][category_id]) > remove_index:
                    elements_data["doc_type_specific"][category_id].pop(remove_index)
                continue

            # 保存（更新）
            if is_multiple:
                if category_id in elements_data["doc_type_specific"]:
                    for i, instance in enumerate(elements_data["doc_type_specific"][category_id]):
                        for field_id in instance:
                            form_field_name = f"element_{category_id}_{i}_{field_id}"
                            if form_field_name in form_data:
                                instance[field_id] = form_data.get(form_field_name, "")
            else: # multipleでない場合
                instance = elements_data["doc_type_specific"].get(category_id)
                if instance:
                    for field_id in instance:
                        form_field_name = f"element_{category_id}_{field_id}"
                        if form_field_name in form_data:
                                instance[field_id] = form_data.get(form_field_name, "")


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

# services.py に追記

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

# services.py（末尾に追記）

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

# services.py（末尾に追記）

from domain_mapper import json_to_intent
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

def score_to_color(score):
    if score is None:
        return "black"
    if score < 0.3:
        return "red"
    if score < 0.6:
        return "orange"
    return "green"

def attach_unit_scores(document: dict) -> None:
    """
    document["units"] に _score を付与する
    （intent / prev / next + 各 color）
    """

    units = document.get("units", [])

    for i, unit in enumerate(units):

        # --- ① intent スコア（仮実装 or 既存関数に置換）
        intent_score = calc_intent_score(document, unit)

        # --- ② 前後接続スコア
        prev_score = None
        next_score = None

        if i > 0:
            prev_score = calc_unit_connection(units[i - 1], unit)
        if i < len(units) - 1:
            next_score = calc_unit_connection(unit, units[i + 1])

        score = {
            "intent": intent_score,
            "prev": prev_score,
            "next": next_score,
        }

        # --- ③ 色付与
        score["intent_color"] = score_to_color(intent_score)
        score["prev_color"] = score_to_color(prev_score)
        score["next_color"] = score_to_color(next_score)

        unit["_score"] = score

def calc_intent_score(document: dict, unit: dict) -> float:
    # 仮：とりあえず全部 0.5
    return 0.5

def calc_unit_connection(unit_a: dict, unit_b: dict) -> float:
    # 仮：とりあえず全部 0.5
    return 0.5

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
    if isinstance(intent["fields"], list):
        intent["fields"] = {
            f.get("key", f"intent_{i}"): {
                "label": f.get("label", ""),
                "value": f.get("value", "")
            }
            for i, f in enumerate(intent["fields"])
        }
