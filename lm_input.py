# llm_input.py
import json
import os
from user_files import get_user_data_path
from typing import Optional
from services.services import DEFAULT_COMPOSITION_META # DEFAULT_COMPOSITION_META をインポート
from ui_labels import UI_LABELS

# ... existing code ...

def build_composition_ideas_prompt(document: dict, composition_meta: dict, user_id: str, target_category_label: Optional[str] = None, suffix: str = "", suggestion_count: int = 3) -> str:
    """
    Builds a prompt for the LLM to generate composition element suggestions.
    If target_category_label is provided, the prompt will be specific to that category.
    The suffix is used for naming generated files.
    """
    doc_type_label = document.get("doc_type", "不明")
    document_title = document.get("title", "不明なドキュメント")
    
    # Map doc_type_label (e.g., "小説") to its internal ID (e.g., "novel")
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in composition_meta["doc_types"].items()}
    doc_type_id = doc_type_mapping.get(doc_type_label, "default") # Use "default" as a fallback ID if not found

    # Dynamically determine template file path
    template_file_name = f"{doc_type_id}.md"
    template_file_path = os.path.join("prompt_templates", template_file_name)

    # --- DEBUG PRINTS ---
    print(f"--- Debugging build_composition_ideas_prompt ---")
    print(f"Received target_category_label: '{target_category_label}'")
    # --- END DEBUG PRINTS ---

    # Fallback to default.md if doc_type specific template does not exist
    if not os.path.exists(template_file_path):
        template_file_path = os.path.join("prompt_templates", "default.md")

    with open(template_file_path, "r", encoding="utf-8") as f:
        template_content = f.read()
    
    intent_fields = document.get("intent", {}).get("fields", {})
    
    # Format intent fields into a readable string
    formatted_intent = ""
    for key, field in intent_fields.items():
        if field.get("label") and field.get("value"):
            formatted_intent += f"- {field['label']}: {field['value']}\n"
    if not formatted_intent:
        formatted_intent = "（作者の意図は特に指定されていません）"

    # Extract composition elements based on all defined categories and format them for the prompt
    elements_text = ""
    has_elements = False

    # Find the target category within the flattened document["composition_elements"]["categories"]
    target_category_data = None
    all_document_categories = document.get("composition_elements", {}).get("categories", []) # 新しいパス

    for category in all_document_categories:
        if category.get("label") == target_category_label:
            target_category_data = category
            break

    if target_category_data and target_category_data.get("elements"):
        elements_text += f"- 分類名: {target_category_data['label']}\n"
        for element in target_category_data["elements"]:
            if element.get("label"):
                elements_text += f"  - 要素名: {element['label']}\n"
                has_elements = True

    if not has_elements:
        elements_text = "（構成要素は定義されていません）\n"

    # Generate the dynamic JSON example for the prompt
    # Pass target_category_label so example is also specific to the category
    dynamic_json_example = _build_dynamic_json_example(document, target_category_label=target_category_label, suggestion_count=suggestion_count)

    # Fill template placeholders
    prompt = template_content.format(
        document_title=document_title,
        doc_type=doc_type_label,
        intent_text=formatted_intent,
        elements_text=elements_text,
        dynamic_json_example=dynamic_json_example,
        suggestion_count=suggestion_count,
        confirmed_plot=f"確定済みの題名: {document.get('selected_title', '未設定')}\n確定済みのプロット: {document.get('selected_plot', '未設定')}"
    )

    # Output the generated prompt to a file for debugging/verification
    user_data_dir = get_user_data_path(user_id)
    os.makedirs(user_data_dir, exist_ok=True) # Ensure the directory exists
    output_file_path = os.path.join(user_data_dir, f"generated_prompt{suffix}.md")
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Generated prompt written to: {output_file_path}")
    except Exception as e:
        print(f"Error writing prompt to file: {e}")

    return prompt

def _get_composition_elements(doc_type_id: str, composition_meta: dict) -> list[str]:
    """
    Extracts a list of composition element labels for a given document type
    from the composition_meta dictionary.
    """
    elements = []
    doc_type_data = composition_meta.get("doc_types", {}).get(doc_type_id)
    if doc_type_data and doc_type_data.get("categories"):
        for category in doc_type_data["categories"]:
            if category.get("elements"):
                for element in category["elements"]:
                    if element.get("label"):
                        elements.append(element["label"])
    return elements

def mock_llm_call(prompt: str, suggestion_count: int = 3) -> dict:
    """
    Mocks an LLM call, returning hardcoded suggestions based on parsed elements.
    In a real scenario, this would call an actual LLM API.
    """
    print(f"Mock LLM called with prompt: {prompt[:200]}...") # Log part of the prompt
    
    mock_suggestions = {"suggestions": {}}
    
    # Extract element labels from the prompt
    elements_section_start = prompt.find("以下に挙げる各構成要素について")
    if elements_section_start != -1:
        elements_section = prompt[elements_section_start:]
        for line in elements_section.split('\n'):
            if line.strip().startswith('- '):
                element_label = line.strip()[2:].strip()
                if element_label:
                    mock_suggestions["suggestions"][element_label] = [f"{element_label}の候補{i+1}" for i in range(suggestion_count)]
    
    # If no specific elements are found or parsed
        mock_suggestions["suggestions"]["汎用構成要素"] = [f"汎用アイデア{i+1}" for i in range(suggestion_count)]
        
    return mock_suggestions

def _build_dynamic_json_example(document: dict, target_category_label: Optional[str] = None, suggestion_count: int = 3) -> str:
    """
    Generates a dynamic JSON example string based on the document's composition elements.
    If target_category_label is provided, the example will be specific to that category.
    This example serves as a strong few-shot example for the LLM.
    """
    dynamic_suggestions_list = []

    all_document_categories = document.get("composition_elements", {}).get("categories", []) # 新しいパス

    for category_obj in all_document_categories:
        category_name = category_obj.get("label")
        if not category_name:
            continue
        
        # Filter by target_category_label if provided
        if target_category_label and category_name != target_category_label:
            continue

        elements_dict = {}
        elements_in_category = category_obj.get("elements")
        if elements_in_category:
            for element_obj in elements_in_category:
                element_label = element_obj.get("label")
                if element_label:
                    # Use generic suggestion placeholders
                    elements_dict[element_label] = [f"提案{i+1}" for i in range(suggestion_count)]
        
        # Only add category if it has elements
        if elements_dict:
            dynamic_suggestions_list.append({
                "category": category_name,
                "elements": elements_dict
            })

    # Wrap in the final "suggestions" structure
    final_json_structure = {"suggestions": dynamic_suggestions_list}

    # Generate JSON string with proper indentation and Japanese character handling
    return json.dumps(final_json_structure, indent=2, ensure_ascii=False)


def build_title_plot_proposals_prompt(document: dict, composition_meta: dict, user_id: str, suffix: str = "", suggestion_count: int = 3) -> str:
    """
    Builds a prompt for the LLM to generate initial title and plot proposals based on
    the "base" category elements in document["composition_elements"].
    """
    template_file_path = os.path.join("prompt_templates", "novel_title_plot_proposals.md")

    with open(template_file_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    intent_fields = document.get("intent", {}).get("fields", {})
    intent_dict = {field.get("label"): field.get("value") for key, field in intent_fields.items() if field.get("label") and field.get("value")}
    formatted_intent_json = json.dumps(intent_dict, indent=2, ensure_ascii=False)

    # --- Extract "base" category elements from document["composition_elements"] for the prompt ---
    elements_text = ""
    dynamic_json_example_for_base = {}
    base_category_label = "基本設定" # composition_meta.json で定義されているラベル (変更なし)

    # document["composition_elements"]["categories"] から "base" カテゴリを探す
    base_category_data = None
    if "composition_elements" in document and "categories" in document["composition_elements"]:
        for category in document["composition_elements"]["categories"]:
            # id が "base" または label が "基本設定" のカテゴリを探す
            if category.get("id") == "base" or category.get("label") == base_category_label:
                base_category_data = category
                break

    if base_category_data and base_category_data.get("elements"):
        elements_text += f"- 分類名: {base_category_data['label']}\n"
        elements_dict = {}
        for element in base_category_data["elements"]:
            if element.get("label"):
                elements_text += f"  - 要素名: {element['label']}\n"
                elements_dict[element["label"]] = [f"提案{i+1}" for i in range(suggestion_count)]
        
        dynamic_json_example_for_base = {
            "suggestions": [{
                "category": base_category_label,
                "elements": elements_dict
            }]
        }
    
    if not elements_text:
        elements_text = "（基本項目は定義されていません）\n"
        dynamic_json_example_for_base = {"suggestions": [{"category": base_category_label, "elements": {}}]}


    # Fill template placeholders
    prompt = template_content.replace("{{ intent }}", formatted_intent_json)
    prompt = prompt.replace("{{ suggestion_count }}", str(suggestion_count))
    prompt = prompt.replace("{elements_text}", elements_text)
    prompt = prompt.replace("{dynamic_json_example}", json.dumps(dynamic_json_example_for_base, indent=2, ensure_ascii=False))

    return prompt

def build_category_composition_prompt(document: dict, composition_meta: dict, user_id: str, category_label: str, suffix: str = "", suggestion_count: int = 1) -> str:
    """
    Builds a prompt for the LLM to generate content for a specific composition category.
    """
    template_file_path = os.path.join("prompt_templates", "category_composition_template.md")

    with open(template_file_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    document_title = document.get("title", "不明なドキュメント")
    doc_type_label = document.get("doc_type", "不明")

    # Author's Intent
    intent_fields = document.get("intent", {}).get("fields", {})
    formatted_intent = ""
    for key, field in intent_fields.items():
        if field.get("label") and field.get("value"):
            formatted_intent += f"- {field['label']}: {field['value']}\n"
    if not formatted_intent:
        formatted_intent = "（作者の意図は特に指定されていません）"

    # Selected Basic Elements
    selected_basic_elements = document.get("selected_basic_elements", {})
    selected_title = selected_basic_elements.get("title", "未設定")
    selected_plot = selected_basic_elements.get("plot", "未設定")

    # Current Composition Elements for context
    elements_text = ""
    all_document_categories = document.get("composition_elements", {}).get("categories", [])
    
    for category_obj in all_document_categories:
        if category_obj.get("label") == category_label:
            elements_text += f"- 分類名: {category_obj['label']}\n"
            if category_obj.get("elements"):
                for element in category_obj["elements"]:
                    if element.get("label"):
                        elements_text += f"  - 要素名: {element['label']}\n"
            break
    if not elements_text:
        elements_text = f"（{category_label}に属する構成要素は定義されていません）"

    # Fill template placeholders
    prompt = template_content.format(
        document_title=document_title,
        doc_type=doc_type_label,
        intent_text=formatted_intent,
        selected_title=selected_title,
        selected_plot=selected_plot,
        elements_text=elements_text,
        category_label=category_label # Pass the specific category label to the prompt
    )

    # Output the generated prompt to a file for debugging/verification
    user_data_dir = get_user_data_path(user_id)
    os.makedirs(user_data_dir, exist_ok=True)
    output_file_path = os.path.join(user_data_dir, f"generated_prompt_{category_label.replace(' ', '_')}_{suffix}.md")
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Generated category composition prompt written to: {output_file_path}")
    except Exception as e:
        print(f"Error writing category composition prompt to file: {e}")

    return prompt

def build_ideal_profile_prompt(document: dict, user_id: str, suggestion_count: int = 3) -> str:
    """
    Builds a prompt for the LLM to generate an ideal profile based on
    author's intent, selected basic elements, composition elements, and semantic label definitions.
    """
    template_file_path = os.path.join("prompt_templates", "ideal_profile.md")

    with open(template_file_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # 1. Collect Author's Intent
    intent_fields = document.get("intent", {}).get("fields", {})
    intent_dict = {field.get("label"): field.get("value") for key, field in intent_fields.items() if field.get("label") and field.get("value")}
    formatted_intent_json = json.dumps(intent_dict, indent=2, ensure_ascii=False)

    # 2. Collect Selected Basic Settings
    selected_basic_elements = document.get("selected_basic_elements", {})
    formatted_selected_basic_elements_json = json.dumps(selected_basic_elements, indent=2, ensure_ascii=False)

    # 3. Collect Elements and Semantic Labels
    elements_and_labels_lines = []
    
    # Load semantic label configuration
    label_config_path = os.path.join("prompt_templates", "novel_label_config.json")
    semantic_label_config = {}
    try:
        with open(label_config_path, "r", encoding="utf-8") as f:
            semantic_label_config = json.load(f).get("labels", {})
    except FileNotFoundError:
        print(f"Warning: {label_config_path} not found. Semantic labels won't be included in prompt.")

    # Iterate through composition elements to get all element labels
    all_document_categories = document.get("composition_elements", {}).get("categories", [])
    
    for category_obj in all_document_categories:
        category_label = category_obj.get("label")
        if not category_label:
            continue
        
        elements_and_labels_lines.append(f"- 分類名: {category_label}")
        
        elements_in_category = category_obj.get("elements")
        if elements_in_category:
            for element_obj in elements_in_category:
                element_label = element_obj.get("label")
                if element_label:
                    elements_and_labels_lines.append(f"  - 要素名: {element_label}")
                    for label_type, label_values in semantic_label_config.items():
                        if label_type == "reader_effect":
                            # For reader_effect, LLM should output a list of labels
                            formatted_values = ", ".join([f"'{k}'" for k in label_values.keys()])
                            elements_and_labels_lines.append(f"    - {label_type} ({UI_LABELS.get(label_type, label_type)}): [リスト形式で、以下のいずれかまたは複数: {formatted_values}]")
                        else:
                            # For scalar labels, output numerical range
                            formatted_values = ", ".join([f"{k}:{v}" for k, v in label_values.items()])
                            elements_and_labels_lines.append(f"    - {label_type} ({UI_LABELS.get(label_type, label_type)}): [{formatted_values}]")
    
    if not elements_and_labels_lines:
        elements_and_labels_lines.append("（物語の構成要素は定義されていません）")
    elements_and_labels_text = "\n".join(elements_and_labels_lines)

    # 4. Construct dynamic_json_example
    example_base_profile = {}
    example_tolerance = {}
    for category_obj in all_document_categories:
        elements_in_category = category_obj.get("elements")
        if elements_in_category:
            for element_obj in elements_in_category:
                element_label = element_obj.get("label")
                if element_label:
                    element_scores = {}
                    element_tolerance = {}
                    for label_type, label_values in semantic_label_config.items():
                        if label_type == "reader_effect":
                            # Example for reader_effect is a list of strings
                            example_effect_list = []
                            if label_values:
                                # Pick a couple of example effects
                                all_effects = list(label_values.keys())
                                if len(all_effects) >= 2:
                                    example_effect_list = [all_effects[0], all_effects[1]]
                                elif len(all_effects) == 1:
                                    example_effect_list = [all_effects[0]]
                            element_scores[label_type] = example_effect_list
                            element_tolerance[label_type] = 1.0 # Tolerance for list of effects can be simple scalar
                        else:
                            # For scalar labels
                            example_score_value = 2 # Default example score within 0-3 range
                            if label_values:
                                # Try to find an existing value within 0-3 range if possible
                                for k, v in label_values.items():
                                    if 0 <= v <= 3:
                                        example_score_value = v
                                        break
                            element_scores[label_type] = example_score_value
                            element_tolerance[label_type] = 1.0 # Example tolerance for scalar

                    example_base_profile[element_label] = element_scores
                    example_tolerance[element_label] = element_tolerance # Add tolerance example per element

    dynamic_json_example_structure = {
        "base_profile": example_base_profile,
        "author_modifier": {},
        "tolerance": example_tolerance # Include an example tolerance
    }
    dynamic_json_example = json.dumps(dynamic_json_example_structure, indent=2, ensure_ascii=False)


    # 5. Fill Template Placeholders
    prompt = template_content.replace("{{ formatted_intent_json }}", formatted_intent_json)
    prompt = prompt.replace("{{ formatted_selected_basic_elements_json }}", formatted_selected_basic_elements_json)
    prompt = prompt.replace("{{ elements_and_labels_text }}", elements_and_labels_text)
    prompt = prompt.replace("{{ dynamic_json_example }}", dynamic_json_example)

    # Output the generated prompt to a file for debugging/verification
    user_data_dir = get_user_data_path(user_id)
    os.makedirs(user_data_dir, exist_ok=True)
    output_file_path = os.path.join(user_data_dir, f"generated_prompt_ideal_profile.md")
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Generated ideal profile prompt written to: {output_file_path}")
    except Exception as e:
        print(f"Error writing ideal profile prompt to file: {e}")

    return prompt