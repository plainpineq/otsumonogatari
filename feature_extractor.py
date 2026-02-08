import json
from typing import List, Dict, Any

class FeatureExtractor:
    """
    意味ラベルを汎用的な数値特徴量（スカラーおよびベクトル）に変換するクラス。
    ラベルの定義はすべて外部のconfigファイルに依存する。
    """
    def __init__(self, config_path: str = 'prompt_templates/novel_label_config.json'):
        """
        コンストラクタ。ラベル設定ファイルを読み込み、特徴量化の準備を行う。
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"設定ファイル '{config_path}' の読み込みに失敗しました: {e}")

        self.scalar_label_maps = {}
        self.vector_label_orders = {}
        self.vector_index_maps = {}

        config_labels = config.get("labels", {})
        for key, value_map in config_labels.items():
            if key == "reader_effect": # Hardcoded as vector based on novel_label.md
                self.vector_label_orders[key] = list(value_map.keys())
                self.vector_index_maps[key] = {value: i for i, value in enumerate(self.vector_label_orders[key])}
            else: # All other labels are treated as scalar
                self.scalar_label_maps[key] = value_map

    def featurize_suggestion(self, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一の構成要素候補を受け取り、汎用的な数値特徴量を付与して返す。
        出力形式: {"scalar_features": {...}, "vector_features": {...}}
        """
        labels = suggestion.get("labels", {})
        
        # --- スカラー特徴量の抽出 ---
        scalar_features = {}
        for key, value_map in self.scalar_label_maps.items():
            label_value_str = labels.get(key)
            # configで定義された数値マッピングに基づき値を取得。対応する値がなければ0をデフォルトとする。
            numerical_value = value_map.get(label_value_str, 0)
            scalar_features[key] = numerical_value
            
        # --- ベクトル特徴量の抽出 ---
        vector_features = {}
        for key, value_order in self.vector_label_orders.items():
            index_map = self.vector_index_maps[key]
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
        if not semantic_labels_list:
            return []
        
        return [self.featurize_suggestion(s) for s in semantic_labels_list]

