import google.genai as genai
import openai
from openai import APIConnectionError
import json
from typing import Optional
import re

def _call_gemini_llm(api_key: str, model_name: str, prompt: str) -> (str, dict):
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
        raw_response_text = response.text # Keep the original raw text
        
        # Find the JSON block using a regular expression
        json_match = re.search(r"```(json)?\s*({.*})\s*```", raw_response_text, re.DOTALL)
        
        if json_match:
            # Extract the JSON string from the regex match
            json_str = json_match.group(2)
        else:
            # If no markdown fence is found, assume the whole response is the JSON string
            json_str = raw_response_text.strip()

        # Parse the extracted JSON string
        parsed_response = json.loads(json_str)
        
        # Return the ORIGINAL raw text and the parsed dictionary
        return raw_response_text, parsed_response
    except Exception as e:
        print(f"Error calling Gemini LLM: {e}")
        raise RuntimeError(f"Failed to get response from Gemini LLM: {e}")

def _call_openai_llm(api_key: str, model_name: str, prompt: str, base_url: Optional[str] = None) -> (str, dict):
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
        raw_response_text = response.choices[0].message.content
        
        # Find the JSON block using a regular expression
        json_match = re.search(r"```(json)?\s*({.*})\s*```", raw_response_text, re.DOTALL)
        
        if json_match:
            # Extract the JSON string from the regex match
            json_str = json_match.group(2)
        else:
            # If no markdown fence is found, assume the whole response is the JSON string
            json_str = raw_response_text.strip()
            
        parsed_response = json.loads(json_str)
        return raw_response_text, parsed_response
    except openai.APIConnectionError as e:
        print(f"Error connecting to OpenAI-compatible LLM at {base_url}: {e}")
        raise RuntimeError(f"LLMサーバーへの接続に失敗しました。URL（{base_url}）が正しいか、サーバーが起動しているか確認してください。")
    except Exception as e:
        print(f"Error calling OpenAI LLM: {e}")
        raise RuntimeError(f"Failed to get response from OpenAI LLM: {e}")

def call_llm(api_key: str, model_name: str, prompt: str, llm_provider: str, base_url: Optional[str] = None) -> (str, dict):
    """
    Dispatches to the appropriate LLM client based on the llm_provider.
    """
    if llm_provider == "gemini":
        return _call_gemini_llm(api_key, model_name, prompt)
    elif llm_provider == "chatgpt":
        # ChatGPT specific logic for model_name and base_url can be added here if needed
        # For now, it will use _call_openai_llm, which is compatible with OpenAI's API
        return _call_openai_llm(api_key, model_name, prompt)
    elif llm_provider == "other":
        # 'other' assumes an OpenAI-compatible API, thus uses _call_openai_llm
        if not base_url:
            raise ValueError("Base URL is required for 'other' LLM provider.")
        return _call_openai_llm(api_key, model_name, prompt, base_url)
    else:
        raise ValueError(f"Unsupported LLM provider: {llm_provider}.")
