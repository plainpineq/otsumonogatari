# scoring.py
from typing import List
from models import Intent


def _keyword_overlap_score(text: str, keywords: List[str]) -> float:
    """
    text に keywords がどれだけ含まれるか（0.0〜1.0）
    """
    if not text or not keywords:
        return 0.0

    text_lower = text.lower()
    hits = sum(1 for k in keywords if k.lower() in text_lower)

    return hits / len(keywords)


def _split_keywords(text: str) -> List[str]:
    """
    日本語対応を考慮した簡易分割
    （将来 MeCab / LLM に差し替え可能）
    """
    if not text:
        return []

    separators = ["、", "。", ",", ".", "・", "\n"]
    for sep in separators:
        text = text.replace(sep, " ")

    return [t.strip() for t in text.split(" ") if t.strip()]


def score_intent_unit_alignment(
    intent: Intent,
    unit_text: str
) -> float:
    """
    Intent と Unit（文章）の整合性スコア
    0.0（不整合）〜 1.0（非常に整合）
    """

    if not unit_text:
        return 0.0

    # --- keyword 準備 ---
    genre_keywords = _split_keywords(intent.genre)
    theme_keywords = _split_keywords(intent.theme_or_claim)
    value_keywords = _split_keywords(intent.core_values)

    # --- 各スコア ---
    genre_score = _keyword_overlap_score(unit_text, genre_keywords)
    theme_score = _keyword_overlap_score(unit_text, theme_keywords)
    values_score = _keyword_overlap_score(unit_text, value_keywords)

    # --- 制約ペナルティ ---
    penalty = 0.0
    for constraint in intent.constraints:
        if constraint and constraint.lower() in unit_text.lower():
            penalty += 0.2  # 1違反あたりのペナルティ

    # --- 重み付き合成 ---
    raw_score = (
        0.25 * genre_score +
        0.35 * theme_score +
        0.40 * values_score
    )

    final_score = max(0.0, raw_score - penalty)

    return round(min(final_score, 1.0), 3)


from typing import Dict, List, Tuple


def generate_onehot_qubo(
    global_target_vector: List[int],
    category_weights: Dict[str, float],
    label_order: List[str],
    penalty: float = 20.0
) -> Dict[Tuple[int, int], float]:
    """
    12ラベル × 6bit = 72変数のOne-hot QUBOを生成する。

    - 各ラベルは0-5の整数
    - One-hot制約 Σ b = 1 を導入
    - 目的関数: Σ w_i (value_i - target_i)^2
    - QUBOは dict[(i,j)] = value 形式で返す（i <= j のみ）
    """

    def expand_weights(
        label_order: List[str],
        category_weights: Dict[str, float]
    ) -> List[float]:
        expanded = []
        for label in label_order:
            category = label.split(":")[0]
            expanded.append(category_weights.get(category, 1.0))
        return expanded

    weights = expand_weights(label_order, category_weights)

    Q: Dict[Tuple[int, int], float] = {}
    var_index = 0
    label_bit_indices: List[List[int]] = []

    # 1. 各ラベルに6ビット割り当て
    for _ in global_target_vector:
        bits = list(range(var_index, var_index + 6))
        label_bit_indices.append(bits)
        var_index += 6

    # 2. 目的関数項
    for i, (target, weight) in enumerate(zip(global_target_vector, weights)):
        bits = label_bit_indices[i]
        for k, bit in enumerate(bits):
            cost = weight * ((k - target) ** 2)
            Q[(bit, bit)] = Q.get((bit, bit), 0.0) + cost

    # 3. One-hot制約: P(Σb - 1)^2
    for bits in label_bit_indices:
        # 対角項: -2P
        for b in bits:
            Q[(b, b)] = Q.get((b, b), 0.0) + (-2.0 * penalty)

        # ペア項: +2P
        for i in range(len(bits)):
            for j in range(i + 1, len(bits)):
                b1 = bits[i]
                b2 = bits[j]
                Q[(b1, b2)] = Q.get((b1, b2), 0.0) + (2.0 * penalty)

    print("=== QUBO Generation Summary ===")
    print("Label count:", len(global_target_vector))
    print("Total binary variables:", var_index)
    print("Non-zero Q terms:", len(Q))

    return Q


def test_qubo_generation() -> None:
    """
    簡易テスト用関数（既存処理には影響しない）
    """

    dummy_target = [3] * 12
    dummy_weights = {
        "CategoryA": 1.0,
        "CategoryB": 1.0,
        "CategoryC": 1.0
    }

    # 実プロジェクトのラベル順に合わせること
    label_order = [
        "CategoryA:Item1", "CategoryA:Item2", "CategoryA:Item3", "CategoryA:Item4",
        "CategoryB:Item1", "CategoryB:Item2", "CategoryB:Item3", "CategoryB:Item4",
        "CategoryC:Item1", "CategoryC:Item2", "CategoryC:Item3", "CategoryC:Item4",
    ]

    Q = generate_onehot_qubo(
        dummy_target,
        dummy_weights,
        label_order
    )

    print("QUBO size:", len(Q))
