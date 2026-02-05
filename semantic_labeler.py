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

# --- 型定義 ---
ChangeType = Literal["A", "B", "C", "D"]
CausalExposure = Literal["A", "B", "C", "D"]
ConflictType = Literal["A", "B", "C", "D"]
ReaderEffect = Literal[
    "違和感", "緊張", "疑問", "驚き", "悲劇性",
    "希望", "安心", "不安", "興味喚起"
]

class LabelSet(Dict):
    change_type: ChangeType
    causal_exposure: CausalExposure
    conflict_type: ConflictType
    reader_effect: List[ReaderEffect]

class LabeledSuggestion(Dict):
    category: str
    element: str
    text: str
    labels: LabelSet

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
    required_keys = {"change_type", "causal_exposure", "conflict_type", "reader_effect"}
    if not required_keys.issubset(labels.keys()):
        logger.warning(f"検証エラー: 必須キーが不足しています。 ({required_keys - set(labels.keys())})")
        return False
    if labels["change_type"] not in ["A", "B", "C", "D"]: return False
    if labels["causal_exposure"] not in ["A", "B", "C", "D"]: return False
    if labels["conflict_type"] not in ["A", "B", "C", "D"]: return False
    if not isinstance(labels["reader_effect"], list): return False
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

def label_suggestions(input_data: Dict[str, Any], llm_config: Dict[str, Any], log_file_path: Optional[str] = None): # -> Generator[LabeledSuggestion, None, None]
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
    
    # 処理終了後、ファイルハンドラを閉じて削除 (メモリリーク防止)
    for handler in logger.handlers[:]: # リストをコピーしてイテレート
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

# --- 実行例 ---
# if __name__ == "__main__":
#     # 入力データ（仕様書通りのサンプル）
#     sample_input = {
#       "llm_suggestions": [
#         {
#           "category": "プロット案_v1",
#           "elements": {
#             "導入": [
#               "古い灯台守の男が、嵐の夜に奇妙な漂着物を発見する。それは未知の文字が刻まれた、光る金属の箱だった。",
#               "都会での生活に疲れた主人公が、祖父の遺した海辺の古い家を訪れる。静かな生活を始めた矢先、浜辺で記憶を失った少女と出会う。"
#             ],
#             "転機": [
#               "主人公が金属の箱を開けてしまうと、灯台の光が消え、村全体が深い霧に包まれてしまう。"
#             ]
#           }
#         }
#       ]
#     }
    
#     # 処理の実行（ログファイル指定なし、コンソールに出力）
#     print("--- ログファイル指定なし (コンソール出力) ---")
#     final_output_console = label_suggestions(sample_input)
    
#     # ログファイル指定ありの例
#     # user_data/test_user/labeler.log に出力
#     test_user_log_path = "user_data/test_user/labeler.log"
#     os.makedirs(os.path.dirname(test_user_log_path), exist_ok=True)
#     print(f"\n--- ログファイル指定あり ({test_user_log_path} に出力) ---")
#     final_output_file = label_suggestions(sample_input, log_file_path=test_user_log_path)
    
#     # 結果の表示 (JSON)
#     print("\n\n--- 最終出力 (JSON) ---")
#     print(json.dumps(final_output_file, indent=2, ensure_ascii=False))
    
#     # 結果の表示 (Pandas DataFrame)
#     try:
#         print("\n--- 最終出力 (DataFrame) ---")
#         df = pd.DataFrame(final_output_file)
        
#         # 'labels'列の辞書をフラットに展開
#         labels_df = pd.json_normalize(df['labels'])
#         df = df.drop('labels', axis=1).join(labels_df)
        
#         print(df)
#     except ImportError:
#         print("Pandasがインストールされていません。`pip install pandas`でインストールすると、結果をテーブル形式で表示できます。")
