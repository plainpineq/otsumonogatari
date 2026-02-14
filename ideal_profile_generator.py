import json
from datetime import datetime
import os
from typing import Dict, Any, List

from flask import session

from services.llm_client import call_llm
from lm_input import build_ideal_profile_prompt
from user_files import get_user_data_path # This will be a new function we create

def generate_ideal_profile(
    document: Dict[str, Any],
    llm_config: Dict[str, Any],
    user_id: str,
    suggestion_count: int = 3 # Default, though not strictly used in current IP gen
) -> Dict[str, Any]:
    """
    Generates an ideal_profile based on document data and LLM configuration.
    """
    if not llm_config:
        raise ValueError("LLM configuration is missing for ideal profile generation.")

    llm_provider = llm_config.get("provider")
    llm_api_key = llm_config.get("api_key")
    llm_model_name = llm_config.get("model_name")
    llm_base_url = llm_config.get("base_url")

    is_config_incomplete = (
        not llm_provider or
        not llm_model_name or
        (llm_provider in ["gemini", "chatgpt"] and not llm_api_key) or
        (llm_provider == "other" and not llm_base_url)
    )

    if is_config_incomplete:
        # For ideal_profile, we might not want to return mock data, but rather
        # ensure the config is complete. Or provide a very basic default.
        # For now, let's raise an error, consistent with app.py's generate_composition.
        raise ValueError("LLM configuration is incomplete for ideal profile generation.")

    # 1. Build the prompt
    prompt = build_ideal_profile_prompt(document, user_id, suggestion_count)

    # 2. Call the LLM
    raw_text, llm_response_json = call_llm(
        llm_api_key, llm_model_name, prompt, llm_provider, base_url=llm_base_url
    )

    # Save raw and structured responses
    user_data_dir = get_user_data_path(session["user_id"])
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    with open(os.path.join(user_data_dir, f"generated_ideal_profile_{timestamp}.txt"), "w", encoding="utf-8") as f:
        f.write(raw_text)
    with open(os.path.join(user_data_dir, f"generated_ideal_profile_{timestamp}.json"), "w", encoding="utf-8") as f:
        json.dump(llm_response_json, f, ensure_ascii=False, indent=2)

    # 3. Format the LLM response into the ideal_profile structure
    # Ensure llm_response_json has the expected 'base_profile'
    if "base_profile" not in llm_response_json:
        raise ValueError("LLM response did not contain 'base_profile' key.")

    ideal_profile_data = {
        "meta": {
            "created_at": datetime.now().isoformat(),
            "version": 1
        },
        "base_profile": llm_response_json["base_profile"],
        "author_modifier": {}, # Initialize as empty
        "tolerance": llm_response_json.get("tolerance", {}) # Save if LLM outputs it
    }

    return ideal_profile_data, raw_text, llm_response_json
