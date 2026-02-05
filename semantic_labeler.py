import json
import time
from typing import List, Dict, Any, Optional, Literal
import random
import pandas as pd
import logging
import os # osモジュールをインポート

from services.llm_client import call_llm # <-- ADDED: Import call_llm

# --- プロンプトテンプレートの読み込み ---
try:
    with open("prompt_templates/novel_label.md", "r", encoding="utf-8") as f:
        PROMPT_TEMPLATE = f.read()
except FileNotFoundError:
    # ログ設定がまだなのでprintを使用
    print("ERROR: プロンプトファイル 'prompt_templates/novel_label.md' が見つかりません。")
    PROMPT_TEMPLATE = "" # フォールバック

# --- ラベル設定の読み込み ---
try:
    with open("prompt_templates/novel_label_config.json", "r", encoding="utf-8") as f:
        LABEL_CONFIG = json.load(f)
except FileNotFoundError:
    print("ERROR: 設定ファイル 'prompt_templates/novel_label_config.json' が見つかりません。")
    LABEL_CONFIG = {"labels": {}} # フォールバック

# 読み込んだ設定から許容される値のリストを生成
ALLOWED_CHANGE_TYPES = list(LABEL_CONFIG.get("labels", {}).get("change_type", {}).keys())
ALLOWED_CAUSAL_EXPOSURES = list(LABEL_CONFIG.get("labels", {}).get("causal_exposure", {}).keys())
ALLOWED_CONFLICT_TYPES = list(LABEL_CONFIG.get("labels", {}).get("conflict_type", {}).keys())
ALLOWED_READER_EFFECTS = list(LABEL_CONFIG.get("labels", {}).get("reader_effect", {}).keys())

class LabelSet(Dict):
    change_type: str
    causal_exposure: str
    conflict_type: str
    reader_effect: List[str]

# --- LLM プロンプト構築 ---
def build_prompt(system_prompt: str, element_name: str, text: str) -> str: # <-- MODIFIED: Added system_prompt
    """LLMに渡すユーザープロンプトを構築します。"""
    if not PROMPT_TEMPLATE:
        return ""
    # JSONの出力形式をMarkdownコードブロックで囲むことで、LLMがより確実にJSONを生成するように促す
    # MODIFIED: Combine system_prompt with PROMPT_TEMPLATE
    user_template_filled = PROMPT_TEMPLATE.format(element_name=element_name, text=text)
    return f"{system_prompt}\n\n{user_template_filled}"


# --- ラベル検証 ---
# loggerインスタンスを引数として受け取るように変更
def validate_labels(logger: logging.Logger, labels: Dict[str, Any]) -> bool:
    """LLMからの応答が期待するスキーマに合致するかを検証します。"""
    # 必須キーを動的に取得
    required_keys = set(LABEL_CONFIG.get("labels", {}).keys())

    if not required_keys.issubset(labels.keys()):
        logger.warning(f"検証エラー: 必須キーが不足しています。 ({required_keys - set(labels.keys())})")
        return False

    # 各ラベルタイプの値を動的に検証
    if "change_type" in labels and labels["change_type"] not in ALLOWED_CHANGE_TYPES:
        logger.warning(f"検証エラー: 不正な change_type 値 '{labels['change_type']}'")
        return False
    if "causal_exposure" in labels and labels["causal_exposure"] not in ALLOWED_CAUSAL_EXPOSURES:
        logger.warning(f"検証エラー: 不正な causal_exposure 値 '{labels['causal_exposure']}'")
        return False
    if "conflict_type" in labels and labels["conflict_type"] not in ALLOWED_CONFLICT_TYPES:
        logger.warning(f"検証エラー: 不正な conflict_type 値 '{labels['conflict_type']}'")
        return False

    # reader_effectはリストであることと、各要素が許容リストに含まれることを確認
    if "reader_effect" in labels:
        if not isinstance(labels["reader_effect"], list):
            logger.warning("検証エラー: reader_effect がリストではありません。")
            return False
        for effect in labels["reader_effect"]:
            if effect not in ALLOWED_READER_EFFECTS:
                logger.warning(f"検証エラー: 不正な reader_effect 要素 '{effect}'")
                return False
    else: # required_keysに含まれていれば、存在しないのはエラー
        if "reader_effect" in required_keys:
             logger.warning("検証エラー: 必須キー 'reader_effect' が不足しています。")
             return False

    return True

# --- メインロジック ---
def get_semantic_labels_from_llm(
    logger: logging.Logger, # loggerインスタンスを引数に追加
    element_name: str, 
    text: str, 
    llm_config: Dict[str, Any], # <-- ADDED: llm_config
    max_retries: int = 3
) -> Optional[LabelSet]:
    """単一のテキストに対してLLMを呼び出し、意味ラベルを取得します。"""
    if not PROMPT_TEMPLATE:
        logger.error("プロンプトテンプレートがロードされていないため、処理を中止します。")
        return None

    system_prompt = "あなたは小説編集者です。文章の良し悪しは評価せず、物語的な役割・性質を分類してください。"
    full_prompt = build_prompt(system_prompt, element_name, text) # <-- MODIFIED: Call new build_prompt
    
    logger.info("--- LLMに送信中 ---")
    logger.info(f"[USER] {full_prompt[:200]}...") # <-- MODIFIED: Log full_prompt
    
    for attempt in range(max_retries):
        try:
            # MODIFIED: Replace mock_llm_api_call with services.llm_client.call_llm
            raw_response, parsed_json = call_llm(
                api_key=llm_config["api_key"],
                model_name=llm_config["model_name"],
                prompt=full_prompt, # <-- MODIFIED: Use full_prompt
                llm_provider=llm_config["provider"],
                base_url=llm_config["base_url"]
            )
            
            if validate_labels(logger, parsed_json): # loggerを渡す
                logger.info("✅ ラベル取得成功")
                return parsed_json
            else:
                logger.warning(f"⚠️ 検証失敗 (試行 {attempt + 1}/{max_retries})")
                
        except (json.JSONDecodeError, ValueError, RuntimeError) as e: # <-- MODIFIED: Added ValueError, RuntimeError
            logger.warning(f"⚠️ LLMの応答形式が不正またはAPI呼び出しエラー (試行 {attempt + 1}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"❌ 予期せぬエラー (試行 {attempt + 1}/{max_retries}): {e}")
        
        time.sleep(1)
        
    logger.error(f"❌ {max_retries}回のリトライに失敗しました。このテキストの処理をスキップします。")
    return None

def label_suggestions(input_data: Dict[str, Any], llm_config: Dict[str, Any], log_file_path: Optional[str] = None): # <-- MODIFIED: Added llm_config and log_file_path
    """
    入力JSON全体を処理し、各候補に意味ラベルを付与するジェネレータ。
    log_file_pathが指定された場合、そのファイルにログを出力します。
    """
    # ロガーの初期化
    logger = logging.getLogger(__name__)
    # 既存のハンドラをクリア（重複出力防止のため）
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.setLevel(logging.INFO)

    if log_file_path:
        # ファイルハンドラを追加
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True) # ディレクトリが存在しない場合作成
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    else:
        # log_file_pathがない場合はコンソールのみに出力 (StreamHandlerを明示的に追加)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(stream_handler)
    
    suggestions = input_data.get("llm_suggestions", [])
    if not suggestions:
        logger.warning("警告: `llm_suggestions` が見つからないか、空です。")
        return

    for suggestion_group in suggestions:
        category = suggestion_group.get("category", "不明なカテゴリ")
        elements = suggestion_group.get("elements", {})
        
        for element_name, texts in elements.items():
            if not isinstance(texts, list):
                continue
            for text in texts:
                logger.info(f"\n--- 処理開始: [{category}]-[{element_name}] ---")
                labels = get_semantic_labels_from_llm(logger, element_name, text, llm_config) # <-- MODIFIED: Pass llm_config
                
                if labels:
                    labeled_result = {
                        "category": category,
                        "element": element_name,
                        "text": text,
                        "labels": labels
                    }
                    yield labeled_result # <-- MODIFIED: Yield result
    
    logger.info("全ての意味ラベル付け処理が完了しました。") # ADDED: Log completion
    
    # 処理終了後、ファイルハンドラを閉じて削除 (メモリリーク防止)
    for handler in logger.handlers[:]: # リストをコピーしてイテレート
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

