import json
import time
from typing import List, Dict, Any, Optional
import logging
import os

from user_files import get_user_data_path # NEW: Import get_user_data_path
from services.llm_client import call_llm

class SemanticLabeler:
    """
    LLMを使用してテキストに意味ラベルを付与し、検証するクラス。
    ラベルの定義はすべて外部のconfigファイルに依存する。
    """
    def __init__(self, config_path="prompt_templates/novel_label_config.json"):
        """
        コンストラクタ。設定ファイルとプロンプトテンプレートを読み込む。
        """
        try:
            with open("prompt_templates/novel_label.md", "r", encoding="utf-8") as f:
                self.prompt_template = f.read()
        except FileNotFoundError:
            logging.error(f"プロンプトファイルが見つかりません: prompt_templates/novel_label.md")
            self.prompt_template = ""

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"設定ファイル '{config_path}' の読み込みに失敗しました: {e}")

        self._initialize_validator()

    def _initialize_validator(self):
        """
        設定ファイルから動的にバリデーション用の情報を生成する。
        """
        self.valid_labels = {}
        self.required_keys = set()
        self.label_types = {} # Add to store if a label is 'scalar' or 'vector'

        config_labels = self.config.get("labels", {})
        for key, values in config_labels.items():
            self.required_keys.add(key)
            if key == "reader_effect": # Hardcoded for now based on prompt_templates/novel_label.md example
                self.label_types[key] = "vector"
                self.valid_labels[key] = list(values.keys()) # Valid choices for vector elements
            else:
                self.label_types[key] = "scalar"
                self.valid_labels[key] = list(values.keys()) # Valid choices for scalar value

    def _validate_labels(self, logger: logging.Logger, labels: Dict[str, Any]) -> bool:
        """
        LLMからの応答がconfigで定義されたスキーマに合致するかを汎用的に検証する。
        """
        if not self.required_keys.issubset(labels.keys()):
            missing_keys = self.required_keys - set(labels.keys())
            logger.warning(f"検証エラー: 必須キーが不足しています。 ({missing_keys})")
            return False

        for key, value in labels.items():
            is_valid_key = key in self.valid_labels
            allowed_values = self.valid_labels.get(key, [])
            label_type = self.label_types.get(key)
            
            if not is_valid_key:
                logger.warning(f"検証エラー: 設定にないキー '{key}' が含まれています。")
                return False

            if label_type == "scalar":
                if not isinstance(value, str):
                    logger.warning(f"検証エラー: キー '{key}' の値は文字列であるべきですが、'{type(value).__name__}' です。")
                    return False
                if value not in allowed_values:
                    logger.warning(f"検証エラー: 不正な値 '{value}' がキー '{key}' に設定されています。許可されている値: {allowed_values}")
                    return False
            elif label_type == "vector":
                if not isinstance(value, list):
                    logger.warning(f"検証エラー: キー '{key}' の値はリストであるべきですが、'{type(value).__name__}' です。")
                    return False
                for item in value:
                    if not isinstance(item, str):
                        logger.warning(f"検証エラー: キー '{key}' のリスト要素は文字列であるべきですが、'{type(item).__name__}' です。")
                        return False
                    if item not in allowed_values:
                        logger.warning(f"検証エラー: 不正なリスト要素 '{item}' がキー '{key}' に含まれています。許可されている値: {allowed_values}")
                        return False
            else:
                logger.error(f"内部エラー: キー '{key}' のラベルタイプが不明です。")
                return False
        
        return True

    def get_semantic_labels_from_llm(
        self,
        logger: logging.Logger,
        element_name: str,
        text: str,
        llm_config: Dict[str, Any],
        user_id: str,
        suffix: str = "",
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        単一のテキストに対してLLMを呼び出し、意味ラベルを取得する。
        """
        if not self.prompt_template:
            logger.error("プロンプトテンプレートがロードされていないため、処理を中止します。")
            return None

        system_prompt = "あなたは小説編集者です。文章の良し悪しは評価せず、物語的な役割・性質を分類してください。"
        user_template_filled = self.prompt_template.format(element_name=element_name, text=text)
        full_prompt = f"{system_prompt}\n\n{user_template_filled}"
        


        logger.info("--- LLMに送信中 ---")
        logger.info(f"[USER] {full_prompt[0:]}...")

        for attempt in range(max_retries):
            try:
                _, parsed_json = call_llm(
                    api_key=llm_config["api_key"],
                    model_name=llm_config["model_name"],
                    prompt=full_prompt,
                    llm_provider=llm_config["provider"],
                    base_url=llm_config["base_url"]
                )
                
                logger.info(f"[LLM] {parsed_json}...")

                if self._validate_labels(logger, parsed_json):
                    logger.info("✅ ラベル取得成功")
                    return parsed_json
                else:
                    logger.warning(f"⚠️ 検証失敗 (試行 {attempt + 1}/{max_retries})")
            except (json.JSONDecodeError, ValueError, RuntimeError) as e:
                logger.warning(f"⚠️ LLMの応答形式が不正またはAPI呼び出しエラー (試行 {attempt + 1}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"❌ 予期せぬエラー (試行 {attempt + 1}/{max_retries}): {e}")
            
            time.sleep(1)
            
        logger.error(f"❌ {max_retries}回のリトライに失敗しました。このテキストの処理をスキップします。")
        return None

def label_suggestions(input_data: Dict[str, Any], llm_config: Dict[str, Any], user_id: str, log_file_path: Optional[str] = None):
    """
    入力JSON全体を処理し、各候補に意味ラベルを付与するジェネレータ。
    進捗情報もyieldする。
    """
    logger = logging.getLogger(__name__)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.setLevel(logging.INFO)

    if log_file_path:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(stream_handler)
    
    try:
        labeler = SemanticLabeler()
    except ValueError as e:
        logger.error(f"初期化エラー: {e}")
        return

    suggestions = input_data.get("llm_suggestions", [])
    if not suggestions:
        logger.warning("警告: `llm_suggestions` が見つからないか、空です。")
        return

    print(f"[LLM] PROVIDER: {llm_config["provider"]}: Model: {llm_config["model_name"]}")

    all_items_to_process = []
    for suggestion_group in suggestions:
        category = suggestion_group.get("category", "不明なカテゴリ")
        elements = suggestion_group.get("elements", {})
        for element_name, texts in elements.items():
            if isinstance(texts, list):
                for text in texts:
                    all_items_to_process.append({
                        "category": category,
                        "element_name": element_name,
                        "text": text
                    })

    total_items = len(all_items_to_process)
    yield {"event": "total_items", "count": total_items} # NEW: Initial total items event

    current_processed_count = 0
    
    try:
        for item_data in all_items_to_process:
            category = item_data["category"]
            element_name = item_data["element_name"]
            text = item_data["text"]

            current_processed_count += 1
            yield {
                "event": "progress",
                "progress_current": current_processed_count,
                "progress_total": total_items,
                "category_label": category,
                "current_element": element_name
            } # NEW: Progress event

            logger.info(f"\n--- 処理開始: [{category}]-[{element_name}] ---")
            # プロンプトファイル名をユニークにするためのsuffixを生成 (iはループ変数でなく、all_items_to_processのインデックスに合わせる)
            file_suffix = f"_{category.replace(' ', '_')}_{element_name.replace(' ', '_')}_{current_processed_count}"
            labels = labeler.get_semantic_labels_from_llm(logger, element_name, text, llm_config, user_id, file_suffix) # user_id と file_suffix を渡す
            
            if labels:
                labeled_result = {
                    "category": category,
                    "element": element_name,
                    "text": text,
                    "labels": labels
                }
                yield {"event": "semantic_label", "data": labeled_result} # NEW: Semantic label event
            else: # LLMからのラベル取得に失敗した場合でもダミーデータをyieldしてapp.pyでカウントを進める
                yield {
                    "event": "semantic_label",
                    "data": {
                        "category": category,
                        "element": element_name,
                        "text": text,
                        "labels": {},
                        "status": "failed" # 失敗したことを示す
                    }
                }
    
    finally:
        logger.info("全ての意味ラベル付け処理が完了しました。")
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                logger.removeHandler(handler)