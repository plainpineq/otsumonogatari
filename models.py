# models.py
from dataclasses import dataclass
from typing import List, Optional


# =========================
# Core Domain Models
# =========================

@dataclass
class Document:
    """
    1つの文章成果物を表す。
    小説・論文・ブログなどを doc_type で区別する。
    """
    id: str
    title: str
    synopsis: str
    doc_type: str  # "novel" | "paper" | "blog"


@dataclass
class Unit:
    """
    Documentを構成する最小の構造単位。
    小説: シーン
    論文: 節 / サブセクション
    ブログ: セクション
    """
    id: str
    document_id: str
    title: str
    summary: str
    order_no: int

    # optional (主に小説用)
    time_start: Optional[int] = None
    time_end: Optional[int] = None
    location: str = ""


@dataclass
class Entity:
    """
    Document内で参照・登場する要素。
    小説: キャラクター
    論文: 概念・手法
    ブログ: 技術・ツール
    """
    id: str
    document_id: str
    name: str
    role: str
    description: str


@dataclass
class Intent:
    """
    作者の意図・思想・制約を表す。
    LLMや最適化は「判断せず、従う」対象。
    """
    document_id: str
    genre: str
    theme_or_claim: str
    values: str
    constraints: List[str]
