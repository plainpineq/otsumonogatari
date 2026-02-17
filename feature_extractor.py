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
            scalar_label_maps = {}
            vector_label_orders = {}
            vector_index_maps = {}

            for key, spec in labels_config.items():
                label_type = spec.get("type")
                values_data = spec.get("values", {})

                if label_type is None:
                    if isinstance(values_data, list):
                        label_type = "vector"
                    elif isinstance(values_data, dict):
                        label_type = "scalar"
                    else:
                        raise ValueError(f"FeatureExtractor: ラベル '{key}' の型が不明です。'type'フィールドを指定するか、'values'フィールドをリストまたは辞書にしてください。")
                
                if label_type == "vector":
                    if isinstance(values_data, list):
                        vector_label_orders[key] = values_data
                    elif isinstance(values_data, dict):
                        vector_label_orders[key] = list(values_data.keys())
                    else:
                        raise ValueError(f"FeatureExtractor: ベクター型ラベル '{key}' の'values'フィールドはリストまたは辞書である必要があります。")
                    vector_index_maps[key] = {value: i for i, value in enumerate(vector_label_orders[key])}
                elif label_type == "scalar":
                    # For scalar, we need a mapping from the string representation to a numerical value (1-5)
                    if isinstance(values_data, dict):
                        # Ensure values are ints for direct use in numerical features
                        scalar_label_maps[key] = {k: int(v) for k, v in values_data.items()}
                    else:
                        raise ValueError(f"FeatureExtractor: スカラー型ラベル '{key}' の'values'フィールドは辞書である必要があります。")
                else:
                    raise ValueError(f"FeatureExtractor: ラベル '{key}' の無効な型 '{label_type}' が指定されました。'scalar'または'vector'を指定してください。")
            
            self.classification_features_specs[classification_name] = {
                "scalar_label_maps": scalar_label_maps,
                "vector_label_orders": vector_label_orders,
                "vector_index_maps": vector_index_maps
            }


    def featurize_suggestion(self, classification: str, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の構成要素候補を受け取り、汎用的な数値特徴量を付与して返す。
        出力形式: {"scalar_features": {...}, "vector_features": {...}}
        """
        if classification not in self.classification_features_specs:
            raise ValueError(f"未知の分類 '{classification}' の特徴量化はできません。")

        specs = self.classification_features_specs[classification]
        scalar_label_maps = specs["scalar_label_maps"]
        vector_label_orders = specs["vector_label_orders"]
        vector_index_maps = specs["vector_index_maps"]

        labels = suggestion.get("labels", {})
        
        # --- スカラー特徴量の抽出 ---
        scalar_features = {}
        for key, value_map in scalar_label_maps.items():
            label_value_int = labels.get(key, 0) # Expecting integer from LLM
            scalar_features[key] = label_value_int
            
        # --- ベクトル特徴量の抽出 ---
        vector_features = {}
        for key, value_order in vector_label_orders.items():
            index_map = vector_index_maps[key]
            # configで定義された順序に基づき、固定長のゼロベクトルを初期化
            feature_vector = [0] * len(value_order)
            
            # 候補のラベルに含まれる各項目に対応するインデックスを1にする
            for label_item in labels.get(key, []):
                if label_item in index_map:
                    feature_vector[index_map[label_item]] = 1
            vector_features[key] = feature_vector

        # 元のキーを維持しつつ、新しい汎用的な 'features' 構造を返す
        return {
            "category": suggestion.get("category"),
            "element": suggestion.get("element"),
            "text": suggestion.get("text"),
            "features": {
                "scalar_features": scalar_features,
                "vector_features": vector_features
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

