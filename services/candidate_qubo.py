from typing import List, Dict, Any, Tuple
import logging

def generate_candidate_selection_qubo(
    semantic_labels: List[Dict[str, Any]],
    evaluation_config: Dict[str, Any],
    label_mapping: Dict[str, Dict[str, str]]
) -> Tuple[Dict[Tuple[int, int], float], List[Dict[str, Any]]]:
    """
    候補選択型QUBOの構築。
    全構成要素を横断して、各要素から1つずつ候補を選択する組み合わせを最適化する。
    
    Q辞書: {(i, j): value} (i <= j)
    """
    # 1. 変数マップの作成
    # 構成要素 (element) ごとに候補 (labels) をフラットに並べる
    variables = [] # List of {cat, el, cand_idx, label_values, qubo_energy}
    element_ranges = [] # List of (start_idx, end_idx)
    
    current_idx = 0
    max_abs_qe = 0.0
    
    for item in semantic_labels:
        cat = item["category"]
        el = item["element"]
        candidates = item["labels"]
        
        start = current_idx
        for k, cand in enumerate(candidates):
            qe = cand.get("qubo_energy", 0.0)
            max_abs_qe = max(max_abs_qe, abs(qe))
            
            variables.append({
                "category": cat,
                "element": el,
                "cand_idx": k,
                "label_values": cand,
                "qubo_energy": qe
            })
            current_idx += 1
        end = current_idx
        element_ranges.append((start, end))

    Q = {}
    
    # 2. 制約: 各要素から必ず1つ選択 (Σ_k x_ik = 1)
    # P * (Σ x - 1)^2 = P * (Σ x^2 + 2Σx_i x_j - 2Σx + 1)
    # Binary x^2 = x => P * (Σ x + 2Σx_i x_j - 2Σx) = P * (2Σx_i x_j - Σx)
    P = 10.0 * max_abs_qe if max_abs_qe > 0 else 10.0
    
    for start, end in element_ranges:
        # 対角項 (Linear): -P * x
        for i in range(start, end):
            Q[(i, i)] = Q.get((i, i), 0.0) - P
        # 二次項 (Interaction): 2P * x_i * x_j
        for i in range(start, end):
            for j in range(i + 1, end):
                Q[(i, j)] = Q.get((i, j), 0.0) + 2.0 * P

    # 3. 一次項 (E1): qubo_energy
    for i, var in enumerate(variables):
        Q[(i, i)] = Q.get((i, i), 0.0) + var["qubo_energy"]

    # 4. 二次項 (E2): ラベル間相互作用 (J_ab * l_a * l_b)
    interactions = evaluation_config.get("interactions", [])
    
    # 異なる構成要素間のみ計算
    for e_idx1, (s1, e1) in enumerate(element_ranges):
        for e_idx2 in range(e_idx1 + 1, len(element_ranges)):
            s2, e2 = element_ranges[e_idx2]
            
            # 要素1の候補 i と 要素2の候補 j のペア
            for i in range(s1, e1):
                for j in range(s2, e2):
                    var_i = variables[i]
                    var_j = variables[j]
                    
                    cat_i = var_i["category"]
                    cat_j = var_j["category"]
                    cand_i = var_i["label_values"]
                    cand_j = var_j["label_values"]
                    
                    for inter in interactions:
                        ka = inter["key_a"]
                        kb = inter["key_b"]
                        strength = inter["strength"]
                        if strength == 0: continue
                        
                        # ka, kb は "Category::EnKey"
                        parts_a = ka.split("::")
                        parts_b = kb.split("::")
                        if len(parts_a) != 2 or len(parts_b) != 2: continue
                        
                        cat_a, en_a = parts_a
                        cat_b, en_b = parts_b
                        
                        val_a = None
                        val_b = None
                        
                        # 候補 i が A かつ 候補 j が B
                        if cat_a == cat_i and cat_b == cat_j:
                            ja_a = label_mapping.get(cat_i, {}).get(en_a)
                            ja_b = label_mapping.get(cat_j, {}).get(en_b)
                            if ja_a in cand_i and ja_b in cand_j:
                                val_a = cand_i[ja_a]
                                val_b = cand_j[ja_b]
                        # 候補 i が B かつ 候補 j が A
                        elif cat_a == cat_j and cat_b == cat_i:
                            ja_a = label_mapping.get(cat_j, {}).get(en_a)
                            ja_b = label_mapping.get(cat_i, {}).get(en_b)
                            if ja_a in cand_j and ja_b in cand_i:
                                val_a = cand_j[ja_a]
                                val_b = cand_i[ja_b]
                        
                        if val_a is not None and val_b is not None:
                            # 正規化: 0-4 -> 0-1
                            contribution = strength * (val_a / 4.0) * (val_b / 4.0)
                            # Q[(i, j)] に蓄積
                            Q[(i, j)] = Q.get((i, j), 0.0) + contribution

    return Q, variables
