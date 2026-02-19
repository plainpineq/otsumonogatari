from typing import List, Dict, Any

def expand_weights(global_label_order: List[tuple], category_weights: Dict[str, float]) -> List[float]:
    """
    (classification, label) のタプル形式の順序リストに基づき、
    各次元に対する重みを生成する。
    """
    expanded = []
    for classification, _ in global_label_order:
        expanded.append(category_weights.get(classification, 1.0))
    return expanded


def weighted_l2(candidate: List[int], target: List[int], weights: List[float]) -> float:
    """
    重み付きL2距離（2乗和）を計算する。
    """
    return sum(
        w * (c - t) ** 2
        for c, t, w in zip(candidate, target, weights)
    )


def apply_tolerance(distance: float, tolerance: float) -> float:
    """
    許容範囲（tolerance）を適用する。
    """
    if distance <= tolerance:
        return 0.0
    return distance - tolerance


def evaluate(candidate_vec: List[int], target_vec: List[int], category_weights: Dict[str, float], label_order: List[tuple], tolerance: float = 0.0):
    """
    統合評価関数。
    """
    weights = expand_weights(label_order, category_weights)
    raw_distance = weighted_l2(candidate_vec, target_vec, weights)
    adjusted = apply_tolerance(raw_distance, tolerance)

    return {
        "raw_distance": raw_distance,
        "adjusted_distance": adjusted
    }


def generate_qubo(target: List[int], weights: List[float]):
    """
    目的関数: min Σ w_i (x_i - t_i)^2
    を最小化するための QUBO 係数を生成する。
    ※ここでは各成分 x_i が 0 or 1 のバイナリ変数の場合を想定。
    (x_i - t_i)^2 = x_i^2 - 2*t_i*x_i + t_i^2
    x_i^2 = x_i (バイナリ変数の特性)
    = (1 - 2*t_i)*x_i + t_i^2
    定数項 t_i^2 は最適化に影響しないため除外。
    """

    Q = {}

    for i, (t, w) in enumerate(zip(target, weights)):
        # 線形項（バイアス）: w * (1 - 2*t)
        # ※要求された形式 Q[(i,)] = -2 * w * t に合わせつつ、w*x_i^2 分を調整
        # 本来バイナリ変数なら x_i^2 = x_i なので係数を合算する。
        
        # 要求されたロジックに基づく実装:
        # 二次項 Q[(i, i)] = w
        Q[(i, i)] = w
        # 線形項 Q[(i,)] = -2 * w * t
        Q[(i,)] = -2 * w * t

    return Q
