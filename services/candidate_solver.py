import random
from typing import Dict, Tuple, List, Any

def solve_candidate_selection_qubo(
    Q: Dict[Tuple[int, int], float],
    variables: List[Dict[str, Any]],
    element_ranges: List[Tuple[int, int]]
) -> Dict[str, Any]:
    """
    候補選択型QUBOのヒューリスティックソルバー。
    Q: QUBO行列 {(i, j): value}
    variables: フラットな候補リスト
    element_ranges: 構成要素ごとのインデックス範囲
    """
    num_vars = len(variables)
    num_elements = len(element_ranges)
    
    if num_elements == 0:
        return {"selection": [], "total_energy": 0, "e1": 0, "e2": 0}

    # 1. 初期解の構築: 各要素から qubo_energy が最小の候補を選ぶ
    # (Qの対角項 - 制約ペナルティP) が実質的なコスト
    current_selection = []
    for start, end in element_ranges:
        best_i = start
        min_cost = float('inf')
        for i in range(start, end):
            # i == j の項を抽出
            cost = Q.get((i, i), 0.0)
            if cost < min_cost:
                min_cost = cost
                best_i = i
        current_selection.append(best_i)

    def calculate_energy_components(selection_indices):
        e1 = 0.0
        e2 = 0.0
        
        # 選択されたビットのみを1としたベクトルを想定
        # E = Σ Q_ii x_i + Σ Q_ij x_i x_j
        
        # selection_indices は変数のグローバルインデックスのリスト
        for i_idx, i in enumerate(selection_indices):
            # 一次項 (もともとの qubo_energy 分を抽出)
            # variables[i]["qubo_energy"] を直接使うのが正確
            e1 += variables[i]["qubo_energy"]
            
            # 二次項 (他の選択された候補との相互作用)
            for j_idx in range(i_idx + 1, len(selection_indices)):
                j = selection_indices[j_idx]
                pair = tuple(sorted((i, j)))
                # Q内の非対角項（制約P以外の寄与分）がE2に相当
                # ここでは単純に Q[(i, j)] を使うが、制約Pを含まないように注意が必要。
                # ただし、i, j が異なる要素に属している限り、Q[(i, j)] は純粋に相互作用 J_ab 由来。
                e2 += Q.get(pair, 0.0)
                
        return e1, e2

    cur_e1, cur_e2 = calculate_energy_components(current_selection)
    best_e1, best_e2 = cur_e1, cur_e2
    best_selection = list(current_selection)

    # 2. 局所探索（ランダムスワップ）
    max_iter = 2000
    for _ in range(max_iter):
        # ランダムに構成要素を1つ選択
        el_idx = random.randint(0, num_elements - 1)
        start, end = element_ranges[el_idx]
        
        if (end - start) <= 1:
            continue
            
        # 別の候補を選択
        old_var_idx = current_selection[el_idx]
        new_var_idx = random.randint(start, end - 1)
        if old_var_idx == new_var_idx:
            continue
            
        # 一時的に変更
        current_selection[el_idx] = new_var_idx
        new_e1, new_e2 = calculate_energy_components(current_selection)
        
        # 改善されたら採用
        if (new_e1 + new_e2) < (best_e1 + best_e2):
            best_e1, best_e2 = new_e1, new_e2
            best_selection = list(current_selection)
        else:
            # 戻す
            current_selection[el_idx] = old_var_idx

    # 結果のデコード (変数のグローバルインデックスを返す)
    return {
        "best_selection_indices": best_selection,
        "total_energy": round(best_e1 + best_e2, 4),
        "e1": round(best_e1, 4),
        "e2": round(best_e2, 4)
    }
