import json
from typing import List, Dict, Any

def _load_label_config(config_path: str = "prompt_templates/novel_label_config.json") -> List[str]:
    """ラベル設定を読み込み、reader_effectの順序リストを返す。"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            label_config = json.load(f)
        return list(label_config.get("labels", {}).get("reader_effect", {}).keys())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"警告: ラベル設定ファイル '{config_path}' の読み込みに失敗しました。 ({e})")
        return []

def _compute_single_fit(candidate_features: Dict[str, Any], 
                        ideal_features: Dict[str, Any],
                        reader_effect_map: List[str]) -> float:
    """
    単一の候補と単一の理想テンプレートとの間のfitスコアを計算する。
    スコアが小さいほど、理想に近いことを示す。
    """
    fit_score = 0.0
    
    # 1. スカラー特徴量の差分を計算 (change, causal, conflict)
    scalar_keys = ["change", "causal", "conflict"]
    for key in scalar_keys:
        candidate_value = candidate_features.get(key, 0)
        ideal_value = ideal_features.get(key, 0)
        fit_score += abs(candidate_value - ideal_value)

    # 2. エフェクト特徴量のペナルティを計算
    # 理想が持つべきエフェクトのセット
    ideal_effects_vector = ideal_features.get("effects", [])
    ideal_effects_present = set()
    for i, score in enumerate(ideal_effects_vector):
        if i < len(reader_effect_map) and score > 0:
            ideal_effects_present.add(reader_effect_map[i])
            
    # 候補が持つエフェクトのセット
    candidate_effects_vector = candidate_features.get("effects", [])
    candidate_effects_present = set()
    for i, score in enumerate(candidate_effects_vector):
        if i < len(reader_effect_map) and score > 0:
            candidate_effects_present.add(reader_effect_map[i])

    # 理想が持つべきエフェクトが候補に存在しない場合にペナルティ (1.0) を加算
    missing_effects = ideal_effects_present - candidate_effects_present
    fit_score += len(missing_effects)

    return fit_score

def apply_fit_to_candidates(candidates: List[Dict[str, Any]], 
                            ideal_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    各候補に対して、最もフィットする理想要素を見つけ、fit情報を付与する。

    Args:
        candidates (List[Dict]): 評価対象となる構成要素候補のリスト。
        ideal_elements (List[Dict]): ユーザーが定義した理想的な構成要素のリスト。

    Returns:
        List[Dict]: 各候補に"fit"辞書が追加されたリスト。
                     例: {"best_fit_element": "転機", "score": 2.5}
    """
    if not candidates or not ideal_elements:
        return candidates

    reader_effect_map = _load_label_config()
    if not reader_effect_map:
        print("警告: reader_effect_mapが空のため、fit計算をスキップします。")
        # 各候補に空のfit情報を設定して返す
        for candidate in candidates:
            candidate["fit"] = {"best_fit_element": "N/A", "score": float('inf')}
        return candidates

    processed_candidates = []
    for candidate in candidates:
        candidate_features = candidate.get("features")
        if not candidate_features:
            candidate["fit"] = {"best_fit_element": "No Features", "score": float('inf')}
            processed_candidates.append(candidate)
            continue

        best_fit_score = float('inf')
        best_fit_element_name = "N/A"

        for ideal in ideal_elements:
            ideal_features = ideal.get("features")
            ideal_name = ideal.get("element", "Unknown")
            if not ideal_features:
                continue

            score = _compute_single_fit(candidate_features, ideal_features, reader_effect_map)
            
            if score < best_fit_score:
                best_fit_score = score
                best_fit_element_name = ideal_name

        candidate["fit"] = {
            "best_fit_element": best_fit_element_name,
            "score": best_fit_score
        }
        processed_candidates.append(candidate)
        
    return processed_candidates
