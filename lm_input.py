from services import list_units, list_entities

def build_llm_input(document, intent):
    units = list_units(document.id)
    entities = list_entities(document.id)

    return {
        "document": {
            "title": document.title,
            "type": document.doc_type
        },
        "intent": {
            "theme_or_claim": intent.theme_or_claim,
            "values": intent.intent_values
        },
        "units": [
            {
                "title": u[2],
                "summary": u[3],
                "order": u[4]
            } for u in units
        ],
        "entities": [
            {
                "name": e[2],
                "role": e[3],
                "description": e[4]
            } for e in entities
        ],
        "constraints": intent.constraints
    }
