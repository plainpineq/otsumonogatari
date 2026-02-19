import json
from datetime import datetime
import os
from typing import Dict, Any, List

from flask import session

from services.llm_client import call_llm
from lm_input import build_ideal_profile_prompt
from user_files import get_user_data_path # This will be a new function we create

from feature_extractor import FeatureExtractor

def build_global_vector(classification: str, scalar_features: Dict[str, Any], extractor: FeatureExtractor) -> List[int]:
    """
    FeatureExtractorを使用して、分類とスカラー特徴量からグローバルベクトルを構築する。
    """
    return extractor.to_global_vector({
        "classification": classification,
        "scalar_features": scalar_features
    })

def generate_ideal_profile(
    document: Dict[str, Any],
    llm_config: Dict[str, Any],
    user_id: str,
    suggestion_count: int = 3
) -> Dict[str, Any]:
    """
    理想の物語構成要素プロファイルを生成し、グローバルベクトルを付与する。
    """
    if not llm_config:
        raise ValueError("LLM configuration is missing for ideal profile generation.")

    llm_provider = llm_config.get("provider")
    llm_api_key = llm_config.get("api_key")
    llm_model_name = llm_config.get("model_name")
    llm_base_url = llm_config.get("base_url")

    # 1. Build the prompt
    prompt = build_ideal_profile_prompt(document, user_id, suggestion_count)

    # 2. Call the LLM
    raw_text, llm_response_json = call_llm(
        llm_api_key, llm_model_name, prompt, llm_provider, base_url=llm_base_url
    )

    # Save raw responses
    user_data_dir = get_user_data_path(session["user_id"])
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    with open(os.path.join(user_data_dir, f"generated_ideal_profile_{timestamp}.json"), "w", encoding="utf-8") as f:
        json.dump(llm_response_json, f, ensure_ascii=False, indent=2)

    if "base_profile" not in llm_response_json:
        raise ValueError("LLM response did not contain 'base_profile' key.")

    # 3. FeatureExtractorによるグローバルベクトルの付与
    extractor = FeatureExtractor()
    augmented_base_profile = {}
    
    # 全要素の合成ベクトルの初期化
    composite_vector = [0] * extractor.get_global_dimension()

    for classification, elements in llm_response_json["base_profile"].items():
        if classification == "scale": continue
        augmented_base_profile[classification] = {}
        
        for element_name, scalar_features in elements.items():
            g_vec = build_global_vector(classification, scalar_features, extractor)
            
            # 構造の維持と拡張
            augmented_base_profile[classification][element_name] = {
                "element": element_name,
                "classification": classification,
                "scalar_features": scalar_features,
                "global_vector": g_vec
            }
            
            # 合成ベクトルの加算 (単純加算)
            for i in range(len(composite_vector)):
                composite_vector[i] += g_vec[i]

    ideal_profile_data = {
        "meta": {
            "created_at": datetime.now().isoformat(),
            "version": 3,
            "dimension": extractor.get_global_dimension()
        },
        "base_profile": augmented_base_profile,
        "author_modifier": {},
        "composite_ideal_vector": composite_vector
    }

    return ideal_profile_data, raw_text, llm_response_json
