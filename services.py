# services.py
import json
import uuid
from typing import List

from db import get_conn
from models import Document, Unit, Entity, Intent


# =========================
# Document
# =========================

def get_document(document_id: str) -> Document:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, synopsis, doc_type FROM story WHERE id=?",
            (document_id,)
        ).fetchone()

    if not row:
        raise ValueError("Document not found")

    return Document(*row)


# =========================
# Unit
# =========================

def list_units(document_id: str) -> List[Unit]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, story_id, title, summary, order_no,
                   time_start, time_end, location
            FROM scene
            WHERE story_id=?
            ORDER BY order_no
        """, (document_id,)).fetchall()

    return [Unit(*row) for row in rows]


def create_unit(
    document_id: str,
    title: str,
    summary: str = "",
    order_no: int = 0
):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO scene
            (id, story_id, title, summary, order_no)
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            document_id,
            title,
            summary,
            order_no
        ))
        conn.commit()


# =========================
# Entity
# =========================

def list_entities(document_id: str) -> List[Entity]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, story_id, name, role, description
            FROM character
            WHERE story_id=?
        """, (document_id,)).fetchall()

    return [Entity(*row) for row in rows]


def create_entity(
    document_id: str,
    name: str,
    role: str,
    description: str = ""
):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO character
            (id, story_id, name, role, description)
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            document_id,
            name,
            role,
            description
        ))
        conn.commit()


# =========================
# Intent (Author Context)
# =========================

def get_intent(document_id: str) -> Intent | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT genre, theme_or_claim, values, constraints
            FROM author_context
            WHERE story_id=?
        """, (document_id,)).fetchone()

    if not row:
        return None

    return Intent(
        document_id=document_id,
        genre=row[0] or "",
        theme_or_claim=row[1] or "",
        values=row[2] or "",
        constraints=json.loads(row[3] or "[]")
    )


def save_intent(intent: Intent):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO author_context
            VALUES (?, ?, ?, ?, ?)
        """, (
            intent.document_id,
            intent.genre,
            intent.theme_or_claim,
            intent.values,
            json.dumps(intent.constraints, ensure_ascii=False)
        ))
        conn.commit()
