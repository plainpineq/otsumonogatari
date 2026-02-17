import json
import os
from typing import List, Dict, Any, Tuple
import math

from feature_extractor import FeatureExtractor # Reusing FeatureExtractor's logic for consistency

class IdealProfileEvaluator:
    """
    ideal_profile に基づいて提案を評価・数値化するクラス。
    """

    def __init__(self, config_path: str = 'prompt_templates/semantic_label_schema.json'):
        """
        コンストラクタ。ラベル設定ファイルを読み込み、FeatureExtractor を初期化する。
        """
        self.feature_extractor = FeatureExtractor(config_path)
        
        # Initialize internal storage for vector label keys, using FeatureExtractor's understanding
        self.vector_label_keys = self.feature_extractor.vector_label_orders.keys()

    def _featurize_ideal_element(self, classification_name: str, element_label: str, ideal_scores: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の理想エレメントのスコアを feature_extractor と互換性のある形式に変換する。
        ideal_scores はLLM出力形式のラベルと数値のペアを想定。
        """
        # FeatureExtractor.featurize_suggestion が期待する形式に合わせる
        # 'labels'キーの下にすべてのラベルを配置し、FeaturExtractorで処理させる
        suggestion = {
            "category": classification_name, # The classification for this ideal element
            "element": element_label,
            "text": f"理想の'{element_label}'",
            "labels": ideal_scores # ideal_scores are essentially the 'labels' for the ideal
        }
        
        # FeatureExtractorの分類別特徴量化ロジックを再利用
        return self.feature_extractor.featurize_suggestion(classification_name, suggestion)

    def convert_ideal_profile_to_features(self, ideal_profile_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        ideal_profile データ全体を、評価計算用の特徴量形式に変換する。
        新しい ideal_profile 構造:
        "base_profile": {
          "シーン案": { "導入": { "劇的強度": 4, ... } },
          "キャラクター案": { "主人公": { "主体性": 5, ... } }
        }
        """
        if "base_profile" not in ideal_profile_data:
            return []

        ideal_elements_with_features = []
        for classification_name, elements_in_classification in ideal_profile_data["base_profile"].items():
            for element_label, ideal_scores in elements_in_classification.items():
                # ここで classification_name を _featurize_ideal_element に渡す
                features = self._featurize_ideal_element(classification_name, element_label, ideal_scores)
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
        candidate_category: str, # NEW: Pass candidate_category to retrieve correct feature specs
        candidate_features: Dict[str, Any], 
        final_ideal_features: Dict[str, Any], 
        tolerance_data: Dict[str, Any]
    ) -> float:
        """
        単一の候補と最終的な理想プロフィールとの間の fit スコアを計算する。
        fit = Σ ((feature - ideal)^2) / tolerance
        """
        fit_score = 0.0

        # Retrieve feature specs for the given candidate_category
        if candidate_category not in self.feature_extractor.classification_features_specs:
            return float('inf') # Should not happen if data is consistent

        specs = self.feature_extractor.classification_features_specs[candidate_category]
        scalar_label_keys = specs["scalar_label_maps"].keys()
        vector_label_keys = specs["vector_label_orders"].keys()
        
        # Scalar Features
        for label_type in scalar_label_keys:
            candidate_value = candidate_features.get("scalar_features", {}).get(label_type, 0)
            ideal_value = final_ideal_features.get("scalar_features", {}).get(label_type, 0)
            
            tolerance = tolerance_data.get(label_type, 1.0)

            if ideal_value is not None:
                fit_score += ((candidate_value - ideal_value) ** 2) / tolerance
            
        # Vector Features
        for vector_label_type in vector_label_keys:
            ideal_vector = final_ideal_features.get("vector_features", {}).get(vector_label_type, [])
            candidate_vector = candidate_features.get("vector_features", {}).get(vector_label_type, [])

            # Ensure vectors are of the same length, pad with zeros if necessary
            # The length is defined by the feature extractor's order for that category
            vector_len = len(specs["vector_label_orders"].get(vector_label_type, []))
            
            ideal_vector_padded = ideal_vector + [0] * (vector_len - len(ideal_vector))
            candidate_vector_padded = candidate_vector + [0] * (vector_len - len(candidate_vector))

            # Sum of squared differences for vector elements
            for i in range(vector_len):
                tolerance_for_vector_type = tolerance_data.get(vector_label_type, 1.0)
                fit_score += ((candidate_vector_padded[i] - ideal_vector_padded[i]) ** 2) / tolerance_for_vector_type

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
        
        ideal_elements_with_features = self.convert_ideal_profile_to_features(ideal_profile_data)
        if not ideal_elements_with_features:
            return candidates_numerical_features

        global_tolerance_data = ideal_profile_data.get("tolerance", {}) 

        processed_candidates = []
        for candidate in candidates_numerical_features:
            candidate_features = candidate.get("features")
            candidate_category = candidate.get("category")

            if not candidate_features or not candidate_category:
                candidate["fit"] = {"best_fit_element": "No Features or Category", "score": float('inf')}
                processed_candidates.append(candidate)
                continue

            best_fit_score = float('inf')
            best_fit_element_name = "N/A"

            # Filter ideal elements by the candidate's category
            relevant_ideal_elements = [
                ideal for ideal in ideal_elements_with_features 
                if ideal.get("category") == candidate_category
            ]

            if not relevant_ideal_elements:
                candidate["fit"] = {"best_fit_element": "No Matching Ideal Category", "score": float('inf')}
                processed_candidates.append(candidate)
                continue

            for ideal_element_features in relevant_ideal_elements:
                ideal_name = ideal_element_features.get("element", "Unknown")

                element_tolerance_data = global_tolerance_data.get(ideal_name, {})

                score = self._compute_single_fit_score(
                    candidate_category, # NEW: Pass candidate_category
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
            candidate_category = candidate.get("category")

            if not candidate_features or not candidate_category:
                candidate["fit"] = {"best_fit_element": "No Features or Category", "score": float('inf')}
                processed_candidates.append(candidate)
                progress = int((i + 1) / total_candidates * 100)
                yield {"progress": progress, "message": f"{i + 1}/{total_candidates} 候補をスキップ中 ({candidate.get('element', '不明な要素')}: 特徴量またはカテゴリ不足)..."}
                continue

            best_fit_score = float('inf')
            best_fit_element_name = "N/A"

            # Filter ideal elements by the candidate's category
            relevant_ideal_elements = [
                ideal for ideal in ideal_elements_with_features 
                if ideal.get("category") == candidate_category
            ]

            if not relevant_ideal_elements:
                candidate["fit"] = {"best_fit_element": "No Matching Ideal Category", "score": float('inf')}
                processed_candidates.append(candidate)
                progress = int((i + 1) / total_candidates * 100)
                yield {"progress": progress, "message": f"{i + 1}/{total_candidates} 候補をスキップ中 ({candidate.get('element', '不明な要素')}: 一致する理想カテゴリなし)..."}
                continue

            for ideal_element_features in relevant_ideal_elements:
                ideal_name = ideal_element_features.get("element", "Unknown")
                element_tolerance_data = global_tolerance_data.get(ideal_name, {})

                score = self._compute_single_fit_score(
                    candidate_category, # NEW: Pass candidate_category
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
            if progress < 100:
                yield {"progress": progress, "message": f"{i + 1}/{total_candidates} 候補を評価中..."}
        
        yield {"progress": 100, "message": "適合度計算が完了しました", "complete": True, "fit_results": processed_candidates}


