import json
import time
from typing import List, Dict, Any, Optional, Literal
import random
import pandas as pd
import logging
import os # osモジュールをインポート

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
def build_prompt(element_name: str, text: str) -> str:
    """LLMに渡すユーザープロンプトを構築します。"""
    if not PROMPT_TEMPLATE:
        return ""
    # JSONの出力形式をMarkdownコードブロックで囲むことで、LLMがより確実にJSONを生成するように促す
    return PROMPT_TEMPLATE.format(element_name=element_name, text=text)

# --- LLM API 呼び出し (モック) ---
# loggerインスタンスを引数として受け取るように変更
def mock_llm_api_call(logger: logging.Logger, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """LLM API呼び出しを模倣する関数。"""
    logger.info("--- LLMに送信中 ---")
    logger.info(f"[SYSTEM] {system_prompt}")
    logger.info(f"[USER] {user_prompt[:200]}...")
    logger.info(f"[CONFIG] temperature={temperature}")
    
    if random.random() < 0.2:
        logger.warning("-> [Mock LLM] 不正なJSONを返却します（リトライテスト）")
        return '{"change_type": "A", "causal_exposure": "B", "conflict_type":, "reader_effect": ["不安"]}'

    dummy_labels = {
        "change_type": random.choice(["A", "B", "C", "D"]),
        "causal_exposure": random.choice(["A", "B", "C", "D"]),
        "conflict_type": random.choice(["A", "B", "C", "D"]),
        "reader_effect": random.sample(
            ["違和感", "緊張", "疑問", "驚き", "悲劇性", "希望", "安心", "不安", "興味喚起"],
            k=random.randint(1, 3)
        )
    }
    
    logger.info(f"-> [Mock LLM] 正常なJSONを返却します: {dummy_labels}")
    time.sleep(0.5)
    return json.dumps(dummy_labels, ensure_ascii=False)

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
    max_retries: int = 3
) -> Optional[LabelSet]:
    """単一のテキストに対してLLMを呼び出し、意味ラベルを取得します。"""
    if not PROMPT_TEMPLATE:
        logger.error("プロンプトテンプレートがロードされていないため、処理を中止します。")
        return None

    system_prompt = "あなたは小説編集者です。文章の良し悪しは評価せず、物語的な役割・性質を分類してください。"
    user_prompt = build_prompt(element_name, text)
    
    for attempt in range(max_retries):
        try:
            response_text = mock_llm_api_call(logger, system_prompt, user_prompt) # loggerを渡す
            parsed_json = json.loads(response_text)
            
            if validate_labels(logger, parsed_json): # loggerを渡す
                logger.info("✅ ラベル取得成功")
                return parsed_json
            else:
                logger.warning(f"⚠️ 検証失敗 (試行 {attempt + 1}/{max_retries})")
                
        except json.JSONDecodeError:
            logger.warning(f"⚠️ JSONパース失敗 (試行 {attempt + 1}/{max_retries})")
        
        time.sleep(1)
        
    logger.error(f"❌ {max_retries}回のリトライに失敗しました。このテキストの処理をスキップします。")
    return None

def label_suggestions(input_data: Dict[str, Any], log_file_path: Optional[str] = None) -> List[LabeledSuggestion]:
    """
    入力JSON全体を処理し、各候補に意味ラベルを付与します。
    log_file_pathが指定された場合、そのファイルにログを出力します。
    """
    # ロガーの初期化
    logger = logging.getLogger(__name__)
    # 既存のハンドラをクリア（重複出力防止のため）
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.setLevel(logging.INFO)

    # StreamHandlerを追加（コンソール出力用、必要に応じて削除）
    # stream_handler = logging.StreamHandler()
    # stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    # logger.addHandler(stream_handler)

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


    labeled_results: List[LabeledSuggestion] = []
    
    suggestions = input_data.get("llm_suggestions", [])
    if not suggestions:
        logger.warning("警告: `llm_suggestions` が見つからないか、空です。")
        return []

    for suggestion_group in suggestions:
        category = suggestion_group.get("category", "不明なカテゴリ")
        elements = suggestion_group.get("elements", {})
        
        for element_name, texts in elements.items():
            if not isinstance(texts, list):
                continue
            for text in texts:
                logger.info(f"\n--- 処理開始: [{category}]-[{element_name}] ---")
                labels = get_semantic_labels_from_llm(logger, element_name, text) # loggerを渡す
                
                if labels:
                    labeled_results.append({
                        "category": category,
                        "element": element_name,
                        "text": text,
                        "labels": labels
                    })
    
    # 処理終了後、ファイルハンドラを閉じて削除 (メモリリーク防止)
    for handler in logger.handlers[:]: # リストをコピーしてイテレート
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

    return labeled_results

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
