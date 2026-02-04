import json
import pandas as pd
from typing import List, Dict, Any, Literal

class FeatureExtractor:
    def __init__(self, config_path: str = 'prompt_templates/novel_label_config.json'):
        """
        FeatureExtractorのコンストラクタ。ラベル設定ファイルを読み込む。

        Args:
            config_path (str): ラベル設定ファイルへのパス。
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
        except json.JSONDecodeError:
            raise ValueError(f"設定ファイルの形式が不正です: {config_path}")

        self.change_type_map = config["labels"]["change_type"]
        self.causal_exposure_map = config["labels"]["causal_exposure"]
        self.conflict_type_map = config["labels"]["conflict_type"]
        self.reader_effect_map = config["labels"]["reader_effect"]

        # reader_effectのベクトル化順序とインデックスマップを動的に生成
        self.reader_effect_vector_order = list(self.reader_effect_map.keys())
        self.reader_effect_index_map = {
            effect: i for i, effect in enumerate(self.reader_effect_vector_order)
        }

    def featurize_suggestion(self, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の構成要素候補（semantic_labelsを含む）を受け取り、
        数値特徴量（features）を付与して返す。
        """
        labels = suggestion.get("labels", {})
        if not labels:
            features = {
                "change": 0, "causal": 0, "conflict": 0,
                "effects": [0] * len(self.reader_effect_vector_order)
            }
        else:
            # マップから値を取得。デフォルト値は0とする。
            # novel_label.md の出力形式に合わせて、キーが存在しない場合は空文字ではなくNoneを想定する。
            # しかし、get()の第二引数はデフォルト値なので、もしLLMが対応するキーを返さなかった場合に
            # どの値をデフォルトとするかは検討が必要。ここでは0をデフォルトとする。
            change_feature = self.change_type_map.get(labels.get("change_type"), 0)
            causal_feature = self.causal_exposure_map.get(labels.get("causal_exposure"), 0)
            conflict_feature = self.conflict_type_map.get(labels.get("conflict_type"), 0)
            
            effects_vector = [0] * len(self.reader_effect_vector_order)
            for effect in labels.get("reader_effect", []):
                if effect in self.reader_effect_index_map:
                    effects_vector[self.reader_effect_index_map[effect]] = 1
            
            features = {
                "change": change_feature, "causal": causal_feature,
                "conflict": conflict_feature, "effects": effects_vector
            }

        return {
            "category": suggestion.get("category"),
            "element": suggestion.get("element"),
            "text": suggestion.get("text"),
            "features": features
        }

    def create_numerical_features(self, semantic_labels_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        semantic_labelsを含む辞書のリストを受け取り、全要素を数値特徴量化する。
        """
        if not semantic_labels_list:
            return []
        return [self.featurize_suggestion(s) for s in semantic_labels_list]


