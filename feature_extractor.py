import json
from typing import List, Dict, Any

class FeatureExtractor:
    """
    意味ラベルを汎用的な数値特徴量（スカラーおよびベクトル）に変換するクラス。
    ラベルの定義はすべて外部のconfigファイルに依存する。
    """
    def __init__(self, config_path: str = 'prompt_templates/semantic_label_schema.json'):
        """
        コンストラクタ。ラベル設定ファイルを読み込み、特徴量化の準備を行う。
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"設定ファイル '{config_path}' の読み込みに失敗しました: {e}")

        self.classification_features_specs = {}

        for classification_name, labels_config in config.items():
            if classification_name == "scale": continue # Skip global scale config

            scalar_label_maps = {}

            for key, spec in labels_config.items():
                label_type = spec.get("type", "scalar")
                values_data = spec.get("values", {})

                if label_type == "scalar":
                    if isinstance(values_data, dict):
                        # Ensure values are ints
                        scalar_label_maps[key] = {k: int(k) for k in values_data.keys()}
                    else:
                        raise ValueError(f"FeatureExtractor: スカラー型ラベル '{key}' の'values'フィールドは辞書である必要があります。")
            
            self.classification_features_specs[classification_name] = {
                "scalar_label_maps": scalar_label_maps
            }


    def featurize_suggestion(self, classification: str, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の構成要素候補を受け取り、数値特徴量（スカラー）を付与して返す。
        未定義ラベルは 0 で埋める。
        """
        if classification not in self.classification_features_specs:
            raise ValueError(f"未知の分類 '{classification}' の特徴量化はできません。")

        specs = self.classification_features_specs[classification]
        scalar_label_maps = specs["scalar_label_maps"]

        # Ensure labels from input is handled correctly
        raw_labels = suggestion.get("labels", {})
        if isinstance(raw_labels, list) and len(raw_labels) > 0:
            labels = raw_labels[0] # Take first if it's a list
        else:
            labels = raw_labels
        
        # --- スカラー特徴量の抽出 ---
        scalar_features = {}
        for key in scalar_label_maps.keys():
            # Get value from labels, default to 0 if not found
            val = labels.get(key, 0)
            try:
                label_value_int = int(val)
            except (ValueError, TypeError):
                label_value_int = 0
            scalar_features[key] = label_value_int
            
        return {
            "category": suggestion.get("category"),
            "element": suggestion.get("element"),
            "text": suggestion.get("text"),
            "features": {
                "scalar_features": scalar_features,
                "vector_features": {} # Keep empty for compatibility or remove
            }
        }

    def create_numerical_features(self, semantic_labels_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        意味ラベルが付与された辞書のリストを受け取り、全要素を数値特徴量化する。
        """
        
        # Group semantic labels by category to process them in batches or ensure category-aware processing
        categorized_features = []
        for suggestion in semantic_labels_list:
            category = suggestion.get("category")
            if not category:
                raise ValueError("semantic_labels_list の各要素には 'category' が含まれている必要があります。")
            
            # Pass the category to featurize_suggestion
            categorized_features.append(self.featurize_suggestion(category, suggestion))
        
        return categorized_features

