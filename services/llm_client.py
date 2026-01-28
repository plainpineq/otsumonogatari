import google.genai as genai
import openai
import json
from typing import Optional

def _call_gemini_llm(api_key: str, model_name: str, prompt: str) -> dict:
    """
    Calls the Google Gemini LLM with the given API key, model name, and prompt.
    Expects the LLM to return a JSON string with a 'suggestions' key.
    """
    if not api_key:
        raise ValueError("Gemini API Key is not configured.")
    if not model_name:
        raise ValueError("Gemini Model Name is not configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    try:
        response = model.generate_content(prompt)
        response_text = response.text
        
        if response_text.startswith("```json"):
            response_text = response_text.strip("```json").strip("```").strip()
        elif response_text.startswith("```"):
            response_text = response_text.strip("```").strip()

        parsed_response = json.loads(response_text)
        return parsed_response
    except Exception as e:
        print(f"Error calling Gemini LLM: {e}")
        raise RuntimeError(f"Failed to get response from Gemini LLM: {e}")

def _call_openai_llm(api_key: str, model_name: str, prompt: str, base_url: Optional[str] = None) -> dict:
    """
    Calls the OpenAI LLM with the given API key, model name, and prompt.
    Expects the LLM to return a JSON string with a 'suggestions' key.
    """
    # If base_url is provided (e.g., for local Ollama), API key might not be strictly required.
    # However, if it's a standard OpenAI endpoint, api_key is essential.
    if not api_key and not base_url:
        raise ValueError("OpenAI API Key is not configured for a standard OpenAI endpoint.")
    if not model_name:
        raise ValueError("OpenAI Model Name is not configured.")

    client = openai.OpenAI(api_key=api_key, base_url=base_url) # Use base_url if provided

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_text = response.choices[0].message.content
        parsed_response = json.loads(response_text)
        return parsed_response
    except Exception as e:
        print(f"Error calling OpenAI LLM: {e}")
        raise RuntimeError(f"Failed to get response from OpenAI LLM: {e}")

def call_llm(api_key: str, model_name: str, prompt: str, base_url: Optional[str] = None) -> dict:
    """
    Dispatches to the appropriate LLM client based on the model name and optional base_url.
    """
    if base_url: # If base_url is provided, assume OpenAI-compatible API
        # Even if it's a Gemini model name, if base_url is given, prioritize OpenAI-compatible client
        return _call_openai_llm(api_key, model_name, prompt, base_url)
    elif model_name.startswith("gpt") or model_name.startswith("text-davinci"):
        return _call_openai_llm(api_key, model_name, prompt)
    elif model_name.startswith("gemini"):
        return _call_gemini_llm(api_key, model_name, prompt)
    else:
        raise ValueError(f"Unsupported LLM model vendor for model: {model_name}. Please specify a valid model name (e.g., 'gemini-pro' or 'gpt-3.5-turbo'), or provide a 'base_url' for OpenAI-compatible APIs.")
