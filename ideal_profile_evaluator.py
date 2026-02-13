import json
import os
from typing import List, Dict, Any, Tuple
import math

from feature_extractor import FeatureExtractor # Reusing FeatureExtractor's logic for consistency

class IdealProfileEvaluator:
    """
    ideal_profile に基づいて提案を評価・数値化するクラス。
    """

    def __init__(self, config_path: str = 'prompt_templates/novel_label_config.json'):
        """
        コンストラクタ。ラベル設定ファイルを読み込み、FeatureExtractor を初期化する。
        """
        self.feature_extractor = FeatureExtractor(config_path)
        
        # Load reader_effect keys for vector mapping
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.reader_effect_keys = list(config.get("labels", {}).get("reader_effect", {}).keys())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"設定ファイル '{config_path}' の読み込みに失敗しました: {e}")

    def _featurize_ideal_element(self, element_label: str, ideal_scores: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の理想エレメントのスコアを feature_extractor と互換性のある形式に変換する。
        """
        scalar_features = {}
        vector_features = {}

        for label_type, value in ideal_scores.items():
            if label_type in self.feature_extractor.scalar_label_maps:
                # スカラー値は直接使用
                scalar_features[label_type] = value
            elif label_type == "reader_effect":
                # reader_effect はリスト形式で来るので、FeatureExtractor と同様にOne-Hotベクトル化
                feature_vector = [0] * len(self.reader_effect_keys)
                if isinstance(value, list):
                    for effect_label in value:
                        if effect_label in self.feature_extractor.vector_index_maps["reader_effect"]:
                            idx = self.feature_extractor.vector_index_maps["reader_effect"][effect_label]
                            feature_vector[idx] = 1
                vector_features[label_type] = feature_vector
            # その他のラベルタイプは無視するか、エラーを発生させる
        
        return {
            "category": "ideal", # カテゴリは理想であることを示す
            "element": element_label,
            "text": f"理想の'{element_label}'",
            "features": {
                "scalar_features": scalar_features,
                "vector_features": vector_features
            }
        }

    def convert_ideal_profile_to_features(self, ideal_profile_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        ideal_profile データ全体を、評価計算用の特徴量形式に変換する。
        """
        if "base_profile" not in ideal_profile_data:
            return []

        ideal_elements_with_features = []
        for element_label, ideal_scores in ideal_profile_data["base_profile"].items():
            features = self._featurize_ideal_element(element_label, ideal_scores)
            ideal_elements_with_features.append(features)
        
        return ideal_elements_with_features

    def calculate_final_ideal(self, base_profile: Dict[str, Any], author_modifier: Dict[str, Any]) -> Dict[str, Any]:
        """
        base_profile と author_modifier を結合し、最終的な理想値を計算する。
        現時点では author_modifier は空なので、base_profile をそのまま返す。
        将来的な拡張のために用意。
        """
        final_ideal = base_profile.copy()
        # 将来的に author_modifier の適用ロジックをここに追加
        return final_ideal

    def _compute_single_fit_score(
        self, 
        candidate_features: Dict[str, Any], 
        final_ideal_features: Dict[str, Any], 
        tolerance_data: Dict[str, Any]
    ) -> float:
        """
        単一の候補と最終的な理想プロフィールとの間の fit スコアを計算する。
        fit = Σ ((feature - ideal)^2) / tolerance
        """
        fit_score = 0.0
        
        # Scalar Features (change_type, causal_exposure, conflict_type)
        for label_type in self.feature_extractor.scalar_label_maps.keys():
            candidate_value = candidate_features.get("scalar_features", {}).get(label_type, 0)
            ideal_value = final_ideal_features.get("scalar_features", {}).get(label_type, 0)
            
            # Get tolerance for this label_type and element
            tolerance = tolerance_data.get(label_type, 1.0) # Default tolerance to 1.0

            # Only add to fit_score if both candidate and ideal have a non-zero value,
            # or if they are both zero and we want to penalize non-existence in idea.
            # For simplicity, calculate difference if ideal_value is present.
            if ideal_value is not None: # Assuming ideal values are always present from base_profile
                fit_score += ((candidate_value - ideal_value) ** 2) / tolerance
            # else: label不足時は無視（ユーザー要件）

        # Vector Features (reader_effect)
        # Apply the same logic as element_fitter.py for consistency
        ideal_effects_vector = final_ideal_features.get("vector_features", {}).get("reader_effect", [])
        ideal_effects_present = set()
        for i, score in enumerate(ideal_effects_vector):
            if i < len(self.reader_effect_keys) and score > 0:
                ideal_effects_present.add(self.reader_effect_keys[i])
                
        candidate_effects_vector = candidate_features.get("vector_features", {}).get("reader_effect", [])
        candidate_effects_present = set()
        for i, score in enumerate(candidate_effects_vector):
            if i < len(self.reader_effect_keys) and score > 0:
                candidate_effects_present.add(self.reader_effect_keys[i])

        # Tolerance for reader_effect should be element-specific and label-specific if defined in tolerance_data
        # For each ideal effect that is missing in candidate, add penalty/tolerance consideration
        for missing_effect in (ideal_effects_present - candidate_effects_present):
            # Check if there's a specific tolerance for this missing_effect
            # If tolerance_data has 'reader_effect' and within it, specific effects, use that.
            # For now, a simple '1.0' penalty if missing, could be scaled by a tolerance value for reader_effect as a whole.
            effect_tolerance = tolerance_data.get("reader_effect", 1.0) # Assume a single tolerance for all effects for now
            fit_score += (1.0 ** 2) / effect_tolerance # Add penalty if missing, squared.

        return fit_score

    def evaluate_and_score_candidates(
        self, 
        candidates_numerical_features: List[Dict[str, Any]], 
        ideal_profile_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        候補の数値特徴量と ideal_profile に基づいて、各候補の fit スコアを計算する。
        """
        if not candidates_numerical_features:
            return []
        
        # 1. Convert ideal_profile to feature format
        ideal_elements_with_features = self.convert_ideal_profile_to_features(ideal_profile_data)
        if not ideal_elements_with_features:
            # ideal_profile が空の場合、fit計算できないため候補をそのまま返す
            return candidates_numerical_features

        # 2. Calculate final_ideal (base_profile + author_modifier) - currently just base_profile
        # Note: final_ideal is currently 'base_profile' from the ideal_profile_data.
        #       author_modifier would modify scores within this final_ideal before featurization.
        #       For simplicity now, we assume base_profile is already the final ideal for featurization.

        # Extract tolerance data per element from ideal_profile_data
        global_tolerance_data = ideal_profile_data.get("tolerance", {}) # This can be per-element or global

        processed_candidates = []
        for candidate in candidates_numerical_features:
            candidate_features = candidate.get("features")
            if not candidate_features:
                candidate["fit"] = {"best_fit_element": "No Features", "score": float('inf')}
                processed_candidates.append(candidate)
                continue

            best_fit_score = float('inf')
            best_fit_element_name = "N/A"

            # Find the best fitting ideal element for this candidate
            for ideal_element_features in ideal_elements_with_features:
                ideal_name = ideal_element_features.get("element", "Unknown")

                # Get element-specific tolerance data, if available.
                # Assuming tolerance in ideal_profile is structured as {element_label: {label_type: value}}
                element_tolerance_data = global_tolerance_data.get(ideal_name, {})

                score = self._compute_single_fit_score(
                    candidate_features, 
                    ideal_element_features.get("features", {}), 
                    element_tolerance_data
                )
                
                if score < best_fit_score:
                    best_fit_score = score
                    best_fit_element_name = ideal_name

            candidate["fit"] = {
                "best_fit_element": best_fit_element_name,
                "score": best_fit_score
            }
            processed_candidates.append(candidate)
            
        return processed_candidates

    def evaluate_and_score_candidates_stream( # New method for streaming progress
        self, 
        candidates_numerical_features: List[Dict[str, Any]], 
        ideal_profile_data: Dict[str, Any]
    ):
        """
        候補の数値特徴量と ideal_profile に基づいて、各候補の fit スコアを計算し、
        進捗状況をストリームで返すジェネレータ。
        """
        if not candidates_numerical_features:
            yield {"progress": 100, "message": "候補がありません", "complete": True, "fit_results": []}
            return
        
        ideal_elements_with_features = self.convert_ideal_profile_to_features(ideal_profile_data)
        if not ideal_elements_with_features:
            yield {"progress": 100, "message": "Ideal Profileが設定されていません", "complete": True, "fit_results": []}
            return

        global_tolerance_data = ideal_profile_data.get("tolerance", {})

        processed_candidates = []
        total_candidates = len(candidates_numerical_features)
        
        yield {"progress": 0, "message": "適合度計算を開始しました"}

        for i, candidate in enumerate(candidates_numerical_features):
            candidate_features = candidate.get("features")
            if not candidate_features:
                candidate["fit"] = {"best_fit_element": "No Features", "score": float('inf')}
                processed_candidates.append(candidate)
                continue

            best_fit_score = float('inf')
            best_fit_element_name = "N/A"

            for ideal_element_features in ideal_elements_with_features:
                ideal_name = ideal_element_features.get("element", "Unknown")
                element_tolerance_data = global_tolerance_data.get(ideal_name, {})

                score = self._compute_single_fit_score(
                    candidate_features, 
                    ideal_element_features.get("features", {}), 
                    element_tolerance_data
                )
                
                if score < best_fit_score:
                    best_fit_score = score
                    best_fit_element_name = ideal_name

            candidate["fit"] = {
                "best_fit_element": best_fit_element_name,
                "score": best_fit_score
            }
            processed_candidates.append(candidate)
            
            progress = int((i + 1) / total_candidates * 100)
            if progress < 100: # Don't send 100% until all processing is done
                yield {"progress": progress, "message": f"{i + 1}/{total_candidates} 候補を評価中..."}
        
        yield {"progress": 100, "message": "適合度計算が完了しました", "complete": True, "fit_results": processed_candidates}


