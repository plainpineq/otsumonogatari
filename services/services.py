# -*- coding: utf-8 -*-
# services.py
import os
from typing import Dict, List
import copy # copyモジュールを追加
import uuid
import json

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
        "units": [], # Initialize as empty, will be populated from composition_meta
        "entities": [],
        "composition_elements": {}, # 新しい構成要素の格納場所
        "composition_meta": copy.deepcopy(DEFAULT_COMPOSITION_META) # デフォルトのメタ定義を追加
    }

    # 日本語の doc_type を英語のキーにマッピング
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in DEFAULT_COMPOSITION_META["doc_types"].items()}
    mapped_doc_type_id = doc_type_mapping.get(doc_type)

    if mapped_doc_type_id:
        doc_type_meta_def = DEFAULT_COMPOSITION_META["doc_types"].get(mapped_doc_type_id)
        if doc_type_meta_def and "categories" in doc_type_meta_def:
            for category_meta in doc_type_meta_def["categories"]:
                if category_meta["id"] == "scene":
                    for element_meta in category_meta.get("elements", []):
                        document["units"].append({"title": element_meta["label"], "content": ""})
                    break # Stop after processing the scene category
    
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
                # ただし、editableがTrueのメタ要素はユーザーが削除可能なので、
                # ここで自動的に再追加しないようにする。
                for element_meta in category_meta.get("elements", []):
                    # editableではないメタ要素のみを強制的に存在させる
                    if not element_meta.get("editable", False):
                        element_found = False
                        for existing_element in existing_elements:
                            if existing_element["id"] == element_meta["id"]:
                                element_found = True
                                # labelも更新される可能性があるのでここで上書き
                                existing_element["label"] = element_meta["label"]
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
    
    # --- Synchronize document["units"] from composition_elements ---
    # This ensures document["units"] reflects the current state of composition_elements,
    # especially the 'scene' category, which functions as the document's structure.
    
    # Find the 'scene' category within the doc_type_specific composition elements
    scene_elements = []
    if mapped_doc_type: # Only attempt if a valid doc_type is mapped
        for category in elements_data.get("doc_type_specific", {}).get("categories", []):
            if category["id"] == "scene":
                scene_elements = category.get("elements", [])
                break
    
    # Regenerate document["units"] based on the current scene_elements
    # Preserve existing content where possible
    new_units = []
    existing_unit_map = {unit["title"]: unit["content"] for unit in document.get("units", [])}

    for element in scene_elements:
        unit_title = element["label"]
        unit_content = existing_unit_map.get(unit_title, "") # Preserve content if title matches
        new_units.append({"title": unit_title, "content": unit_content})
    
    document["units"] = new_units


def update_composition_elements(document: dict, form_data) -> None:

    elements_data = document["composition_elements"]
    composition_meta = document["composition_meta"] # documentからcomposition_metaを取得

    # 日本語の doc_type を英語のキーにマッピング
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in composition_meta["doc_types"].items()}
    mapped_doc_type = doc_type_mapping.get(document["doc_type"])

    # --- 共通構成要素の処理 ---
    common_categories = elements_data["common"].setdefault("categories", [])
    for current_category_data in common_categories:
        category_id = current_category_data["id"]
        elements = current_category_data.setdefault("elements", [])

        # --- 要素の追加 ---
        if f"add_element_{category_id}" in form_data:
            new_element = {
                "id": str(uuid.uuid4().hex[:8]), # 一時的なユニークID
                "label": "新しい項目", # デフォルトラベル
                "value": "",
                "editable": True
            }
            elements.append(new_element)

        # Identify the exact delete button that was clicked
        clicked_delete_id = None
        # Iterate through all elements in the *current* category
        for element in elements:
            # Construct the expected form_key for this element's delete button
            expected_form_key = f"remove_element_{category_id}_{element.get('id')}"
            if expected_form_key in form_data:
                # And if its value matches the element's ID (double-check)
                if form_data.get(expected_form_key) == element.get('id'):
                    clicked_delete_id = element.get('id')
                    break # Found the specific button clicked
        
        if clicked_delete_id:
            elements[:] = [elem for elem in elements if elem.get("id") != clicked_delete_id]

        # --- 要素の更新 ---
        # Iterate through elements in the document data, and for each, check if its label/value was updated in form_data
        for element in elements:
            element_id = element.get("id")

            # labelの更新
            form_label_name = f"element_label_{category_id}_{element_id}"
            if form_label_name in form_data:
                element["label"] = form_data.get(form_label_name, "")

            # valueの更新 (if such fields exist in HTML, current HTML doesn't show them but it's good for consistency)
            form_value_name = f"element_value_{category_id}_{element_id}"
            if form_value_name in form_data:
                element["value"] = form_data.get(form_value_name, "")

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

            # Identify the exact delete button that was clicked
            clicked_delete_id = None
            for element in elements:
                expected_form_key = f"remove_element_{category_id}_{element.get('id')}"
                if expected_form_key in form_data:
                    if form_data.get(expected_form_key) == element.get('id'):
                        clicked_delete_id = element.get('id')
                        break
            
            if clicked_delete_id:
                elements[:] = [elem for elem in elements if elem.get("id") != clicked_delete_id]
            
            # --- 要素の更新 ---
            for element in elements:
                element_id = element.get("id")

                # labelの更新
                form_label_name = f"element_label_{category_id}_{element_id}"
                if form_label_name in form_data:
                    element["label"] = form_data.get(form_label_name, "")

                # valueの更新 (if such fields exist in HTML, current HTML doesn't show them but it's good for consistency)
                form_value_name = f"element_value_{category_id}_{element_id}"
                if form_value_name in form_data:
                    element["value"] = form_data.get(form_value_name, "")


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
