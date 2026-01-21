from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Document:
    id: str
    title: str
    synopsis: str
    doc_type: str  # novel / paper / blog

@dataclass
class Unit:
    id: str
    document_id: str
    title: str
    summary: str
    order_no: int
    time_start: Optional[int] = None
    time_end: Optional[int] = None

@dataclass
class Entity:
    id: str
    document_id: str
    name: str
    role: str
    description: str

@dataclass
class Intent:
    document_id: str
    genre: str
    theme_or_claim: str
    intent_values: str
    constraints: list

