# llm_input.py
import json
# from services.services import (
#     get_document,
#     list_units,
#     list_entities,
#     get_intent
# )


# The original build_llm_input function, commented out due to missing imports.
# If this function is needed in the future, it will need to be refactored
# to use existing service functions like find_document and process the
# passed-in document dictionary.
# def build_llm_input(document_id: str) -> dict:
#     document = get_document(document_id)
#     units = list_units(document_id)
#     entities = list_entities(document_id)
#     intent = get_intent(document_id)

#     return {
#         "document": {
#             "id": document.id,
#             "title": document.title,
#             "type": document.doc_type,
#             "synopsis": document.synopsis
#         },
#         "intent": {
#             "theme_or_claim": intent.theme_or_claim if intent else "",
#             "values": intent.values if intent else "",
#             "genre": intent.genre if intent else ""
#         },
#         "constraints": intent.constraints if intent else [],
#         "units": [
#             {
#                 "title": u.title,
#                 "summary": u.summary,
#                 "order": u.order_no
#             } for u in units
#         ],
#         "entities": [
#             {
#                 "name": e.name,
#                 "role": e.role,
#                 "description": e.description
#             } for e in entities
#         ]
#     }

def build_composition_ideas_prompt(document: dict) -> str:
    """
    Builds a prompt for the LLM to generate composition element suggestions.
    """
    intent_fields = document.get("intent", {}).get("fields", {})
    doc_type = document.get("doc_type", "不明")

    # Format intent fields into a readable string
    formatted_intent = ""
    for key, field in intent_fields.items():
        if field.get("label") and field.get("value"):
            formatted_intent += f"- {field['label']}: {field['value']}\n"
    if not formatted_intent:
        formatted_intent = "（作者の意図は特に指定されていません）"

    prompt = f"""
あなたはプロの物語構成エディターです。
以下のドキュメント情報と作者の意図に基づき、物語の構成要素（プロット、キャラクター属性、世界観の要素など）を5〜10個提案してください。
各提案は、具体的で創造的なタイトルとして短くまとめてください。

---
ドキュメント種別: {doc_type}

作者の意図:
{formatted_intent}
---

提案はJSON形式で、キーは "suggestions"、値は提案の文字列の配列として出力してください。
例:
{{
    "suggestions": [
        "主人公の過去の秘密",
        "クライマックスでの予期せぬ裏切り",
        "魔法システムの詳細なルール",
        "主要キャラクターの成長アーク",
        "物語の舞台となる都市の歴史的背景"
    ]
}}
"""
    return prompt

def mock_llm_call(prompt: str) -> list[str]:
    """
    Mocks an LLM call, returning hardcoded suggestions.
    In a real scenario, this would call an actual LLM API.
    """
    print(f"Mock LLM called with prompt: {prompt[:200]}...") # Log part of the prompt
    
    # Simulate different responses based on doc_type or intent if needed
    if "小説" in prompt:
        return {
            "suggestions": [
                "主人公の隠された過去",
                "ライバルとの因縁",
                "物語を左右するキーアイテム",
                "予期せぬ第三勢力の介入",
                "感情の対比によるシーン構成",
                "舞台となる異世界の風習"
            ]
        }
    elif "論文" in prompt:
        return {
            "suggestions": [
                "研究目的の明確化",
                "先行研究との比較分析",
                "実験方法の具体的な記述",
                "結果の統計的考察",
                "結論の新規性と貢献度"
            ]
        }
    else:
        return {
            "suggestions": [
                "汎用アイデア1",
                "汎用アイデア2",
                "汎用アイデア3",
                "汎用アイデア4",
                "汎用アイデア5"
            ]
        }