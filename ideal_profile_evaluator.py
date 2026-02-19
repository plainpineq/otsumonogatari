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

    def _featurize_ideal_element(self, classification_name: str, element_label: str, ideal_scores: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の理想エレメントのスコアを feature_extractor と互換性のある形式に変換する。
        """
        suggestion = {
            "category": classification_name,
            "element": element_label,
            "text": f"理想の'{element_label}'",
            "labels": ideal_scores
        }
        return self.feature_extractor.featurize_suggestion(classification_name, suggestion)

    def convert_ideal_profile_to_features(self, ideal_profile_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        ideal_profile データ全体を、評価計算用の特徴量形式に変換する。
        """
        if "base_profile" not in ideal_profile_data:
            return []

        ideal_elements_with_features = []
        for classification_name, elements_in_classification in ideal_profile_data["base_profile"].items():
            if classification_name == "scale": continue
            for element_label, ideal_scores in elements_in_classification.items():
                features = self._featurize_ideal_element(classification_name, element_label, ideal_scores)
                ideal_elements_with_features.append(features)
        
        return ideal_elements_with_features

    def calculate_final_ideal(self, base_profile: Dict[str, Any], author_modifier: Dict[str, Any]) -> Dict[str, Any]:
        """
        base_profile と author_modifier を結合し、最終的な理想値を計算する。
        """
        final_ideal = base_profile.copy()
        return final_ideal

    def _compute_single_fit_score(
        self, 
        candidate_category: str,
        candidate_features: Dict[str, Any], 
        final_ideal_features: Dict[str, Any]
    ) -> float:
        """
        単一の候補と最終的な理想プロフィールとの間の fit スコアを計算する。
        fit = Σ ((feature - ideal)^2) / 1.0 (system fixed tolerance)
        """
        fit_score = 0.0

        candidate_scalars = candidate_features.get("scalar_features", {})
        ideal_scalars = final_ideal_features.get("scalar_features", {})
        
        # Scalar Features (now only scalars exist)
        for label_type, ideal_value in ideal_scalars.items():
            candidate_value = candidate_scalars.get(label_type, 0)
            # tolerance = system (1.0)
            fit_score += ((candidate_value - ideal_value) ** 2)

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

                score = self._compute_single_fit_score(
                    candidate_category,
                    candidate_features, 
                    ideal_element_features.get("features", {})
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

    def evaluate_and_score_candidates_stream(
        self, 
        candidates_numerical_features: List[Dict[str, Any]], 
        ideal_profile_data: Dict[str, Any]
    ):
        """
        進捗状況をストリームで返すジェネレータ。
        """
        if not candidates_numerical_features:
            yield {"progress": 100, "message": "候補がありません", "complete": True, "fit_results": []}
            return
        
        ideal_elements_with_features = self.convert_ideal_profile_to_features(ideal_profile_data)
        if not ideal_elements_with_features:
            yield {"progress": 100, "message": "Ideal Profileが設定されていません", "complete": True, "fit_results": []}
            return

        processed_candidates = []
        total_candidates = len(candidates_numerical_features)
        
        yield {"progress": 0, "message": "適合度計算を開始しました"}

        for i, candidate in enumerate(candidates_numerical_features):
            candidate_features = candidate.get("features")
            candidate_category = candidate.get("category")

            if not candidate_features or not candidate_category:
                candidate["fit"] = {"best_fit_element": "No Features or Category", "score": float('inf')}
                processed_candidates.append(candidate)
                yield {"progress": int((i + 1) / total_candidates * 100), "message": f"{i + 1}/{total_candidates} スキップ中..."}
                continue

            best_fit_score = float('inf')
            best_fit_element_name = "N/A"

            relevant_ideal_elements = [
                ideal for ideal in ideal_elements_with_features 
                if ideal.get("category") == candidate_category
            ]

            if not relevant_ideal_elements:
                candidate["fit"] = {"best_fit_element": "No Matching Ideal Category", "score": float('inf')}
                processed_candidates.append(candidate)
                yield {"progress": int((i + 1) / total_candidates * 100), "message": f"{i + 1}/{total_candidates} 一致カテゴリなし..."}
                continue

            for ideal_element_features in relevant_ideal_elements:
                ideal_name = ideal_element_features.get("element", "Unknown")

                score = self._compute_single_fit_score(
                    candidate_category,
                    candidate_features, 
                    ideal_element_features.get("features", {})
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


