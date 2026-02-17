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

    def __init__(self, config_path="prompt_templates/semantic_label_schema.json"):

        """

        コンストラクタ。設定ファイルとプロンプトテンプレートを読み込む。

        """

        try:

            with open("prompt_templates/classification_batch_evaluation.md", "r", encoding="utf-8") as f:

                self.batch_evaluation_prompt_template = f.read()

        except FileNotFoundError:

            logging.error(f"バッチ評価プロンプトファイルが見つかりません: prompt_templates/classification_batch_evaluation.md")

            self.batch_evaluation_prompt_template = ""



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

        self.classification_specs = {} # Stores validation info per classification



        for classification_name, labels_config in self.config.items():

            valid_labels = {}

            required_keys = set()

            label_types = {}

            evaluation_items_definitions = [] # For prompt generation



            for key, spec in labels_config.items():

                required_keys.add(key)

                

                label_type = spec.get("type")

                values_data = spec.get("values", {})

                description = spec.get("description", "")



                if label_type is None:

                    if isinstance(values_data, list):

                        label_type = "vector"

                    elif isinstance(values_data, dict):

                        label_type = "scalar"

                    else:

                        raise ValueError(f"ラベル '{key}' の型が不明です。'type'フィールドを指定するか、'values'フィールドをリストまたは辞書にしてください。")

                

                label_types[key] = label_type



                if label_type == "vector":

                    if isinstance(values_data, list):

                        valid_labels[key] = values_data

                    elif isinstance(values_data, dict):

                        valid_labels[key] = list(values_data.keys())

                    else:

                        raise ValueError(f"ベクター型ラベル '{key}' の'values'フィールドはリストまたは辞書である必要があります。")

                    evaluation_items_definitions.append(f"- {key} ({description}): [リスト形式で、以下のいずれかまたは複数: {', '.join(valid_labels[key])}]")

                elif label_type == "scalar":

                    if isinstance(values_data, dict):

                        valid_labels[key] = list(values_data.keys()) # Store keys for validation

                    else:

                        raise ValueError(f"スカラー型ラベル '{key}' の'values'フィールドは辞書である必要があります。")

                    evaluation_items_definitions.append(f"- {key} ({description}): [1（{values_data.get('1', '最低')}）-5（{values_data.get('5', '最高')}）の整数値]")

                else:

                    raise ValueError(f"ラベル '{key}' の無効な型 '{label_type}' が指定されました。'scalar'または'vector'を指定してください。")

            

            self.classification_specs[classification_name] = {

                "valid_labels": valid_labels,

                "required_keys": required_keys,

                "label_types": label_types,

                "evaluation_items_definitions": "\n".join(evaluation_items_definitions)

            }



    def _validate_labels(self, logger: logging.Logger, classification_name: str, labels: Dict[str, Any]) -> bool:

        """

        LLMからの応答がconfigで定義されたスキーマに合致するかを汎用的に検証する。

        """

        if classification_name not in self.classification_specs:

            logger.warning(f"検証エラー: 未知の分類名 '{classification_name}' です。")

            return False



        specs = self.classification_specs[classification_name]

        required_keys = specs["required_keys"]

        valid_labels = specs["valid_labels"]

        label_types = specs["label_types"]



        if not required_keys.issubset(labels.keys()):

            missing_keys = required_keys - set(labels.keys())

            logger.warning(f"検証エラー: 必須キーが不足しています。 ({missing_keys})")

            return False



        for key, value in labels.items():

            is_valid_key = key in valid_labels

            allowed_values = valid_labels.get(key, [])

            label_type = label_types.get(key)

            

            if not is_valid_key:

                logger.warning(f"検証エラー: 設定にないキー '{key}' が含まれています。")

                return False



            if label_type == "scalar":

                # Ensure it's an integer between 1 and 5

                if not isinstance(value, int) or not (1 <= value <= 5):

                    logger.warning(f"検証エラー: スカラー型ラベル '{key}' の値は1から5の整数であるべきですが、'{type(value).__name__}' または範囲外です。")

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



    def _evaluate_classification_candidates_with_llm(

        self,

        logger: logging.Logger,

        classification_name: str,

        candidates: Dict[str, List[str]], # e.g., {"導入": ["テキスト1", "テキスト2"], "日常": [...]}

        llm_config: Dict[str, Any],

        user_id: str,

        max_retries: int = 3

    ) -> Optional[Dict[str, Dict[str, Any]]]: # e.g., {"導入": {ラベル: 数値}, "日常": {...}}

        """

        指定された分類に属する複数の候補を一括でLLMに評価させ、結果を返す。

        """

        if classification_name not in self.classification_specs:

            logger.error(f"未知の分類名 '{classification_name}' の評価はできません。")

            return None

        

        if not self.batch_evaluation_prompt_template:

            logger.error("バッチ評価プロンプトテンプレートがロードされていないため、処理を中止します。")

            return None



        specs = self.classification_specs[classification_name]

        evaluation_items_definitions = specs["evaluation_items_definitions"]



        # Build output JSON example

        output_json_example_dict = {}

        first_candidate_name = next(iter(candidates.keys()), "候補1")

        example_labels = {}

        for key, label_type in specs["label_types"].items():

            if label_type == "scalar":

                example_labels[key] = 3 # Example scalar value

            elif label_type == "vector":

                example_labels[key] = ["例1", "例2"] # Example vector value

        output_json_example_dict[first_candidate_name] = example_labels

        output_json_example = json.dumps(output_json_example_dict, indent=2, ensure_ascii=False)



        # Flatten candidates for prompt as "候補名: テキスト" format, but keep the original candidates structure for JSON input to LLM

        # For the prompt, we'll represent it as a JSON block with element_name as key and all its texts as list values

        candidates_for_prompt_dict = {

            element_name: [text_item for text_item in texts]

            for element_name, texts in candidates.items()

        }

        candidates_json = json.dumps(candidates_for_prompt_dict, indent=2, ensure_ascii=False)



        full_prompt = self.batch_evaluation_prompt_template.format(

            classification_name=classification_name,

            evaluation_items_definitions=evaluation_items_definitions,

            candidates_json=candidates_json,

            output_json_example=output_json_example

        )

        

        # Save generated prompt for debugging

        user_data_dir = get_user_data_path(user_id)

        os.makedirs(user_data_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        prompt_file_path = os.path.join(user_data_dir, f"generated_evaluation_prompt_{classification_name.replace(' ', '_')}_{timestamp}.md")

        try:

            with open(prompt_file_path, "w", encoding="utf-8") as f:

                f.write(full_prompt)

            logger.info(f"Generated evaluation prompt written to: {prompt_file_path}")

        except Exception as e:

            logger.error(f"Error writing evaluation prompt to file: {e}")



        logger.info(f"--- LLMに送信中 ({classification_name}の候補群) ---")

        logger.info(f"[USER] {full_prompt[:500]}...") # Log part of the prompt



        for attempt in range(max_retries):

            try:

                _, parsed_json_response = call_llm(

                    api_key=llm_config["api_key"],

                    model_name=llm_config["model_name"],

                    prompt=full_prompt,

                    llm_provider=llm_config["provider"],

                    base_url=llm_config["base_url"]

                )

                

                logger.info(f"[LLM] {json.dumps(parsed_json_response, ensure_ascii=False)[:500]}...")



                # Validate each candidate's labels in the batch response

                all_valid = True

                validated_results = {}

                for candidate_name, labels in parsed_json_response.items():

                    if candidate_name not in candidates:

                        logger.warning(f"検証エラー: LLM応答に、評価依頼していない候補 '{candidate_name}' が含まれています。")

                        all_valid = False

                        break

                    if not self._validate_labels(logger, classification_name, labels):

                        all_valid = False

                        break

                    validated_results[candidate_name] = labels



                if all_valid:

                    logger.info("✅ バッチラベル取得成功")

                    return validated_results

                else:

                    logger.warning(f"⚠️ バッチ検証失敗 (試行 {attempt + 1}/{max_retries})")

            except (json.JSONDecodeError, ValueError, RuntimeError) as e:

                logger.warning(f"⚠️ LLMの応答形式が不正またはAPI呼び出しエラー (試行 {attempt + 1}/{max_retries}): {e}")

            except Exception as e:

                logger.error(f"❌ 予期せぬエラー (試行 {attempt + 1}/{max_retries}): {e}")

            

            time.sleep(1) # Wait before retrying

            

        logger.error(f"❌ {max_retries}回のリトライに失敗しました。この分類の処理をスキップします。")

        return None



def label_suggestions(input_data: Dict[str, Any], llm_config: Dict[str, Any], user_id: str, log_file_path: Optional[str] = None):
    """
    入力JSON全体を処理し、各分類の候補群に意味ラベルを付与するジェネレータ。
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

    all_classification_batches = []
    total_candidates_to_process = 0

    # Group candidates by classification
    for suggestion_group in suggestions:
        classification_name = suggestion_group.get("category", "不明な分類")
        if classification_name not in labeler.classification_specs:
            logger.warning(f"警告: 未知の分類名 '{classification_name}' はスキップします。")
            continue

        elements_dict = suggestion_group.get("elements", {})
        candidates_for_llm_batch = {}
        for element_name, texts in elements_dict.items():
            if isinstance(texts, list) and texts:
                # Join all texts for an element into a single string for LLM evaluation
                candidates_for_llm_batch[element_name] = "\n".join(texts)
                total_candidates_to_process += 1
            elif isinstance(texts, str): # Handle single string candidates directly
                candidates_for_llm_batch[element_name] = texts
                total_candidates_to_process += 1
        
        if candidates_for_llm_batch:
            all_classification_batches.append({
                "classification_name": classification_name,
                "candidates": candidates_for_llm_batch
            })

    yield {"event": "total_items", "count": total_candidates_to_process}

    current_processed_count = 0
    all_results = []
    
    try:
        for batch_info in all_classification_batches:
            classification_name = batch_info["classification_name"]
            candidates_for_llm = batch_info["candidates"]

            logger.info(f"\n--- 処理開始: 分類 '{classification_name}' の候補群 ---")
            
            # Call the new batch evaluation method
            batch_evaluation_results = labeler._evaluate_classification_candidates_with_llm(
                logger=logger,
                classification_name=classification_name,
                candidates=candidates_for_llm,
                llm_config=llm_config,
                user_id=user_id
            )

            if batch_evaluation_results:
                for element_name, labels in batch_evaluation_results.items():
                    # Find the original text(s) for this element_name to include in the result
                    original_texts = []
                    for sg in suggestions:
                        if sg.get("category") == classification_name:
                            original_texts = sg.get("elements", {}).get(element_name, [])
                            if isinstance(original_texts, str): # Ensure it's a list for consistency
                                original_texts = [original_texts]
                            break
                    
                    labeled_result = {
                        "category": classification_name,
                        "element": element_name,
                        "text": "\n".join(original_texts), # Store the joined original texts
                        "labels": labels
                    }
                    all_results.append(labeled_result)
                    yield {"event": "semantic_label", "data": labeled_result}
                    current_processed_count += 1
                    yield {
                        "event": "progress",
                        "progress_current": current_processed_count,
                        "progress_total": total_candidates_to_process,
                        "category_label": classification_name,
                        "current_element": element_name
                    }
            else:
                # If batch evaluation for a classification fails, yield dummy failed results
                for element_name in candidates_for_llm.keys():
                    original_texts = []
                    for sg in suggestions:
                        if sg.get("category") == classification_name:
                            original_texts = sg.get("elements", {}).get(element_name, [])
                            if isinstance(original_texts, str):
                                original_texts = [original_texts]
                            break
                    
                    yield {
                        "event": "semantic_label",
                        "data": {
                            "category": classification_name,
                            "element": element_name,
                            "text": "\n".join(original_texts),
                            "labels": {},
                            "status": "failed"
                        }
                    }
                    current_processed_count += 1
                    yield {
                        "event": "progress",
                        "progress_current": current_processed_count,
                        "progress_total": total_candidates_to_process,
                        "category_label": classification_name,
                        "current_element": element_name
                    }
            
    finally:
        logger.info("全ての意味ラベル付け処理が完了しました。")
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                logger.removeHandler(handler)