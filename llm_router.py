import logging
from typing import Dict, Any, Optional
from services.llm_client import call_llm

def generate_draft(prompt: str, llm_config: Dict[str, Any]) -> str:
    """
    LLMを使用して小説の下書き（ドラフト）を生成します。
    llm_config には、provider, model, api_key などの設定が含まれます。
    """
    provider = llm_config.get("provider", "openai")
    model_name = llm_config.get("model", "gpt-4o")
    api_key = llm_config.get("api_key", "")
    base_url = llm_config.get("base_url")

    # call_llm は (raw_text, parsed_json) を返す。
    # 通常、ドラフト生成は構造化データ（JSON）を期待しないテキスト生成だが、
    # call_llm の既存実装に合わせる。
    
    # provider が chatgpt か openai かを正規化
    if provider == "openai":
        provider = "chatgpt"
    
    try:
        logging.info(f"[LLM Router] Generating draft with provider: {provider}, model: {model_name}")
        
        # NOTE: 既存の call_llm は JSON 応答を前提とした re.search を行っている可能性があるため、
        # ドラフト生成専用のシンプル版が必要になるかもしれないが、
        # 要件「既存のAPI呼び出しコードがあればそれを流用」に従い、call_llm を利用。
        
        raw_text, _ = call_llm(
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            llm_provider=provider,
            base_url=base_url
        )
        
        return raw_text
    except Exception as e:
        logging.error(f"[LLM Router] Error during draft generation: {e}")
        raise RuntimeError(f"下書き生成に失敗しました: {e}")
