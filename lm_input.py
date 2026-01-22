# llm_input.py
from services.services import (
    get_document,
    list_units,
    list_entities,
    get_intent
)


def build_llm_input(document_id: str) -> dict:
    document = get_document(document_id)
    units = list_units(document_id)
    entities = list_entities(document_id)
    intent = get_intent(document_id)

    return {
        "document": {
            "id": document.id,
            "title": document.title,
            "type": document.doc_type,
            "synopsis": document.synopsis
        },
        "intent": {
            "theme_or_claim": intent.theme_or_claim if intent else "",
            "values": intent.values if intent else "",
            "genre": intent.genre if intent else ""
        },
        "constraints": intent.constraints if intent else [],
        "units": [
            {
                "title": u.title,
                "summary": u.summary,
                "order": u.order_no
            } for u in units
        ],
        "entities": [
            {
                "name": e.name,
                "role": e.role,
                "description": e.description
            } for e in entities
        ]
    }
