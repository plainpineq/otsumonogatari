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


def calculate_energy_detail(semantic_labels: Dict[str, Dict[str, int]], evaluation_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    一次項（E1）と二次項（E2）を分解したエネルギー計算。
    """
    # 1. ラベルのフラット化
    flat_labels = {}
    for category, labels in semantic_labels.items():
        for label, value in labels.items():
            flat_labels[f"{category}::{label}"] = value

    # 柔軟なキー取得 (Prompt定義 vs 既存実装)
    target_values = evaluation_config.get("target_values", evaluation_config.get("targets", {}))
    weights = evaluation_config.get("weights", {})
    category_weights = evaluation_config.get("category_weights", {})
    interactions = evaluation_config.get("interactions", [])

    # 2. & 3. 一次項計算 (E1)
    E1 = 0.0
    E1_details = []

    for key, value in flat_labels.items():
        if key not in target_values:
            continue
        
        target = target_values[key]
        
        # 重みの決定: 個別重み優先、なければカテゴリ重み、それもなければ1.0
        weight = weights.get(key)
        if weight is None:
            category = key.split("::")[0]
            weight = category_weights.get(category, 1.0)
        
        # 正規化
        x_norm = value / 4.0
        t_norm = target / 4.0
        
        contribution = weight * ((x_norm - t_norm) ** 2)
        E1 += contribution
        
        E1_details.append({
            "key": key,
            "value": round(contribution, 4)
        })

    # 4. 二次項計算 (E2)
    E2 = 0.0
    E2_details = []

    for inter in interactions:
        key_a = inter.get("key_a")
        key_b = inter.get("key_b")
        strength = inter.get("strength", 0.0)
        
        if key_a in flat_labels and key_b in flat_labels:
            val_a = flat_labels[key_a]
            val_b = flat_labels[key_b]
            
            # 正規化
            x_norm_a = val_a / 4.0
            x_norm_b = val_b / 4.0
            
            contribution = strength * x_norm_a * x_norm_b
            E2 += contribution
            
            E2_details.append({
                "key_a": key_a,
                "key_b": key_b,
                "value": round(contribution, 4)
            })

    # 5. 総エネルギー
    total = E1 + E2

    # 6. 割合計算
    if total != 0:
        ratio1 = (E1 / total) * 100
        ratio2 = (E2 / total) * 100
    else:
        ratio1 = 0.0
        ratio2 = 0.0

    # 7. 詳細割合計算
    # 一次項
    for item in E1_details:
        if E1 != 0:
            item["ratio"] = round((item["value"] / E1) * 100, 2)
        else:
            item["ratio"] = 0.0

    # 二次項
    abs_sum_e2 = sum(abs(item["value"]) for item in E2_details)
    for item in E2_details:
        if abs_sum_e2 > 0:
            item["ratio"] = round((abs(item["value"]) / abs_sum_e2) * 100, 2)
        else:
            item["ratio"] = 0.0

    # 9. ソート
    E1_details.sort(key=lambda x: x["value"], reverse=True)
    E2_details.sort(key=lambda x: abs(x["value"]), reverse=True)

    # 10. 戻り値
    return {
        "total": round(total, 4),
        "E1": round(E1, 4),
        "E2": round(E2, 4),
        "ratio1": round(ratio1, 2),
        "ratio2": round(ratio2, 2),
        "E1_details": E1_details,
        "E2_details": E2_details
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
