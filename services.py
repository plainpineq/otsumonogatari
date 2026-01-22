# services.py
import os
from typing import Dict, List

from structure_templates import STRUCTURE_TEMPLATES


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
        "entities": []
    }

    data.setdefault("documents", []).append(document)
    return document


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
    Intent（作者の思想・制約）を更新する
    """
    constraints_text = form_data.get("constraints", "")

    document["intent"] = {
        "genre": form_data.get("genre", ""),
        "theme_or_claim": form_data.get("theme_or_claim", ""),
        "core_values": form_data.get("core_values", ""),
        "constraints": [
            line.strip()
            for line in form_data.get("constraints", "").splitlines()
            if line.strip()
        ]
    }

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
from scoring import score_intent_unit_alignment
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
