#!/usr/bin/env python3
import os
import sys
import json
import requests

# Global variables for providers and rotation state
_PROVIDERS = []
_CURRENT_IDX = 0

def load_env_file(filepath=".env"):
    """Loads environment variables from a .env file if it exists."""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        val = val.strip().strip("'\"")
                        os.environ[key.strip()] = val

def init_keys():
    """Initializes the rotating provider pool from keys.json or GEMINI_API_KEY env var."""
    global _PROVIDERS, _CURRENT_IDX
    load_env_file()
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    keys_json_path = os.path.join(project_root, "keys.json")
    
    _PROVIDERS = []
    
    # Try loading keys.json
    if os.path.exists(keys_json_path):
        try:
            with open(keys_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Parse Gemini keys
            gemini_keys = data.get("gemini", [])
            for key in gemini_keys:
                if key:
                    _PROVIDERS.append({
                        "type": "gemini",
                        "key": key
                    })
                    
            # Parse OpenAI-compatible providers
            openai_comps = data.get("openai_compatible", [])
            for item in openai_comps:
                if isinstance(item, dict) and item.get("key") and item.get("base_url") and item.get("model"):
                    _PROVIDERS.append({
                        "type": "openai_compatible",
                        "key": item["key"],
                        "base_url": item["base_url"],
                        "model": item["model"]
                    })
        except Exception as e:
            print(f"Warning: Failed to load keys.json: {e}", file=sys.stderr)
            
    # Fallback to GEMINI_API_KEY environment variable if pool is empty
    if not _PROVIDERS:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            _PROVIDERS.append({
                "type": "gemini",
                "key": api_key
            })
            
    _CURRENT_IDX = 0

def get_response(prompt, is_mock=False, mock_response=None):
    """Gets a response from the provider pool, rotating through them on failure.
    
    Caps consecutive failures at 3, returning an alert if reached.
    """
    if is_mock:
        if mock_response is not None:
            return mock_response
        return "Mock response from model."

    global _PROVIDERS, _CURRENT_IDX
    
    if not _PROVIDERS:
        init_keys()
        
    if not _PROVIDERS:
        return "ALERT: No Gemini or OpenAI-compatible API keys found. Set GEMINI_API_KEY environment variable or create keys.json."

    consecutive_failures = 0
    max_failures = min(3, len(_PROVIDERS))

    while consecutive_failures < max_failures:
        provider = _PROVIDERS[_CURRENT_IDX]
        p_type = provider["type"]
        
        try:
            if p_type == "gemini":
                # Dispatch to Gemini API
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={provider['key']}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": prompt
                        }]
                    }]
                }
                
                print(f"Trying Gemini API key index {_CURRENT_IDX}...", file=sys.stderr)
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return text
                elif response.status_code == 429:
                    print(f"Warning: Gemini API key index {_CURRENT_IDX} rate limited (429). Rotating...", file=sys.stderr)
                else:
                    print(f"Warning: Gemini API key index {_CURRENT_IDX} failed with HTTP {response.status_code}. Rotating...", file=sys.stderr)
                    
            elif p_type == "openai_compatible":
                # Dispatch to OpenAI-compatible Chat Completions API
                base_url = provider["base_url"].rstrip("/")
                url = f"{base_url}/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {provider['key']}"
                }
                payload = {
                    "model": provider["model"],
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                
                print(f"Trying OpenAI-compatible model '{provider['model']}' at index {_CURRENT_IDX}...", file=sys.stderr)
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    return text
                elif response.status_code == 429:
                    print(f"Warning: OpenAI-compatible model index {_CURRENT_IDX} rate limited (429). Rotating...", file=sys.stderr)
                else:
                    print(f"Warning: OpenAI-compatible model index {_CURRENT_IDX} failed with HTTP {response.status_code}. Rotating...", file=sys.stderr)
                    
        except Exception as e:
            print(f"Warning: Provider index {_CURRENT_IDX} request failed: {e}. Rotating...", file=sys.stderr)
            
        consecutive_failures += 1
        _CURRENT_IDX = (_CURRENT_IDX + 1) % len(_PROVIDERS)

    return "ALERT: All Gemini keys exhausted. Check your API balances."

# Automatically initialize keys on module load
init_keys()
