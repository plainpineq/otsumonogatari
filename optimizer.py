# optimizer.py
import math
import random
from typing import List

from models import Intent
from services.scoring import score_intent_unit_alignment
from connection_scoring import total_connection_score


def total_intent_alignment_score(intent: Intent, units: List[dict]) -> float:
    """
    Intent × Unit 整合性スコア（合計）
    """
    return sum(
        score_intent_unit_alignment(intent, u.get("content", ""))
        for u in units
    )


def total_story_score(intent: Intent, units: List[dict]) -> float:
    """
    物語全体の総合スコア
    """
    intent_score = total_intent_alignment_score(intent, units)
    connection_score = total_connection_score(units)

    # 重み（調整可能）
    return (
        0.6 * intent_score +
        0.4 * connection_score
    )


def optimize_unit_order(
    intent: Intent,
    units: List[dict],
    iterations: int = 500,
    start_temp: float = 1.0,
    end_temp: float = 0.01
) -> List[dict]:
    """
    擬似アニーリングによる Unit 並び順最適化
    """

    if len(units) < 2:
        return units

    current = units[:]
    best = units[:]

    current_score = total_story_score(intent, current)
    best_score = current_score

    for step in range(iterations):
        temp = start_temp + (end_temp - start_temp) * (step / iterations)

        i, j = random.sample(range(len(units)), 2)
        neighbor = current[:]
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]

        neighbor_score = total_story_score(intent, neighbor)
        delta = neighbor_score - current_score

        if delta > 0 or random.random() < math.exp(delta / temp):
            current = neighbor
            current_score = neighbor_score

            if current_score > best_score:
                best = neighbor
                best_score = neighbor_score

    return best
