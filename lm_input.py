# llm_input.py
import json
import os
from user_files import get_user_data_path

# ... existing code ...

def build_composition_ideas_prompt(document: dict, composition_meta: dict, user_id: str) -> str:
    """
    Builds a prompt for the LLM to generate composition element suggestions.
    """
    doc_type_label = document.get("doc_type", "不明")
    document_title = document.get("title", "不明なドキュメント")
    
    # Map doc_type_label (e.g., "小説") to its internal ID (e.g., "novel")
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in composition_meta["doc_types"].items()}
    doc_type_id = doc_type_mapping.get(doc_type_label, "default") # Use "default" as a fallback ID if not found

    # Dynamically determine template file path
    template_file_name = f"{doc_type_id}.md"
    template_file_path = os.path.join("prompt_templates", template_file_name)

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
    elements_text = "" # Start with an empty string
    
    has_elements = False

    # Helper function to append categories and elements
    def append_elements_to_text(categories_data):
        nonlocal has_elements
        nonlocal elements_text # Declare elements_text as nonlocal
        if categories_data:
            for category in categories_data:
                elements_text_local = "" # Use a local string to check if elements are added
                if category.get("elements"):
                    elements_text_local += f"- 分類名: {category['label']}\n" # Category heading
                    for element in category["elements"]:
                        if element.get("label"):
                            elements_text_local += f"  - 要素名: {element['label']}\n" # Indented element
                            has_elements = True
                    elements_text += elements_text_local

    # Process common categories
    common_categories = document.get("composition_elements", {}).get("common", {}).get("categories")
    append_elements_to_text(common_categories)

    # Process doc_type_specific categories
    doc_type_specific_categories = document.get("composition_elements", {}).get("doc_type_specific", {}).get("categories")
    append_elements_to_text(doc_type_specific_categories)
    
    if not has_elements:
        elements_text = "（構成要素は定義されていません）\n"

    # Generate the dynamic JSON example for the prompt
    dynamic_json_example = _build_dynamic_json_example(document)

    # Fill template placeholders
    prompt = template_content.format(
        document_title=document_title,
        doc_type=doc_type_label, # Use the human-readable label for the prompt
        intent_text=formatted_intent,
        elements_text=elements_text,
        dynamic_json_example=dynamic_json_example # New placeholder
    )

    # Output the generated prompt to a file for debugging/verification
    user_data_dir = get_user_data_path(user_id)
    os.makedirs(user_data_dir, exist_ok=True) # Ensure the directory exists
    output_file_path = os.path.join(user_data_dir, "generated_prompt.md")
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

def mock_llm_call(prompt: str) -> dict:
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
                    mock_suggestions["suggestions"][element_label] = [f"{element_label}の候補{i+1}" for i in range(5)]
    
    # If no specific elements are found or parsed
        mock_suggestions["suggestions"]["汎用構成要素"] = [f"汎用アイデア{i+1}" for i in range(5)]
        
    return mock_suggestions

def _build_dynamic_json_example(document: dict) -> str:
    """
    Generates a dynamic JSON example string based on the document's composition elements.
    This example serves as a strong few-shot example for the LLM.
    """
    dynamic_suggestions_list = []

    # Helper to process categories (common or doc_type_specific)
    def process_categories(categories_data):
        if not categories_data:
            return

        for category_obj in categories_data:
            category_name = category_obj.get("label")
            if not category_name:
                continue

            elements_dict = {}
            elements_in_category = category_obj.get("elements")
            if elements_in_category:
                for element_obj in elements_in_category:
                    element_label = element_obj.get("label")
                    if element_label:
                        # Use generic suggestion placeholders
                        elements_dict[element_label] = [f"提案{i+1}" for i in range(5)]
            
            # Only add category if it has elements
            if elements_dict:
                dynamic_suggestions_list.append({
                    "category": category_name,
                    "elements": elements_dict
                })

    # Process common categories
    common_categories = document.get("composition_elements", {}).get("common", {}).get("categories")
    process_categories(common_categories)

    # Process doc_type_specific categories
    doc_type_specific_categories = document.get("composition_elements", {}).get("doc_type_specific", {}).get("categories")
    process_categories(doc_type_specific_categories)
    
    # Wrap in the final "suggestions" structure
    final_json_structure = {"suggestions": dynamic_suggestions_list}

    # Generate JSON string with proper indentation and Japanese character handling
    # Escaping curly braces for Python's .format() is not needed here
    # as this string is already the final JSON.
    return json.dumps(final_json_structure, indent=2, ensure_ascii=False)