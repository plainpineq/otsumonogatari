# connection_scoring.py
from typing import List


def _tokenize(text: str) -> List[str]:
    """
    非依存・軽量トークナイザ
    """
    if not text:
        return []

    separators = ["、", "。", ",", ".", "・", "\n"]
    for sep in separators:
        text = text.replace(sep, " ")

    return [t.strip().lower() for t in text.split(" ") if t.strip()]


def _jaccard_similarity(a: List[str], b: List[str]) -> float:
    """
    Jaccard 類似度（0.0〜1.0）
    """
    set_a = set(a)
    set_b = set(b)

    if not set_a or not set_b:
        return 0.0

    return len(set_a & set_b) / len(set_a | set_b)


def score_unit_connection(unit_a_text: str, unit_b_text: str) -> float:
    """
    Unit A → Unit B の接続スコア
    """
    tokens_a = _tokenize(unit_a_text)
    tokens_b = _tokenize(unit_b_text)

    lexical_score = _jaccard_similarity(tokens_a, tokens_b)
    topic_score = _jaccard_similarity(tokens_a[-10:], tokens_b[:10])

    len_a = len(tokens_a)
    len_b = len(tokens_b)

    if max(len_a, len_b) == 0:
        length_score = 0.0
    else:
        length_score = 1.0 - abs(len_a - len_b) / max(len_a, len_b)

    final_score = (
        0.4 * lexical_score +
        0.4 * topic_score +
        0.2 * length_score
    )

    return round(final_score, 3)


def total_connection_score(units: List[dict]) -> float:
    """
    Unit 配列全体の接続スコア（隣接ペア合計）
    """
    if len(units) < 2:
        return 0.0

    score = 0.0
    for i in range(len(units) - 1):
        score += score_unit_connection(
            units[i].get("content", ""),
            units[i + 1].get("content", "")
        )

    return round(score, 3)
