import uuid
from db import get_conn
from structure_templates import STRUCTURE_TEMPLATES

def create_units_from_template(document_id, doc_type):
    titles = STRUCTURE_TEMPLATES.get(doc_type, [])
    with get_conn() as conn:
        for i, title in enumerate(titles, start=1):
            conn.execute("""
            INSERT INTO scene (id, story_id, title, summary, order_no)
            VALUES (?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), document_id, title, "", i
            ))
        conn.commit()

def list_units(document_id):
    with get_conn() as conn:
        return conn.execute("""
        SELECT * FROM scene WHERE story_id=?
        ORDER BY order_no
        """, (document_id,)).fetchall()

def list_entities(document_id):
    with get_conn() as conn:
        return conn.execute("""
        SELECT * FROM character WHERE story_id=?
        """, (document_id,)).fetchall()
