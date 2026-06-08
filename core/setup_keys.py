#!/usr/bin/env python3
import os
import json
import sys

def get_keys_path():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "keys.json")

def load_keys():
    keys_path = get_keys_path()
    default_structure = {"gemini": [], "openai_compatible": []}
    if not os.path.exists(keys_path):
        return default_structure
    try:
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default_structure
            if "gemini" not in data or not isinstance(data["gemini"], list):
                data["gemini"] = []
            if "openai_compatible" not in data or not isinstance(data["openai_compatible"], list):
                data["openai_compatible"] = []
            return data
    except Exception:
        return default_structure

def save_keys(data):
    keys_path = get_keys_path()
    try:
        with open(keys_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving keys.json: {e}")
        return False

def mask_key(key):
    if not key:
        return "None"
    key_str = str(key).strip()
    if len(key_str) <= 4:
        return "..." + key_str
    return "..." + key_str[-4:]

def get_provider_name_from_url(url):
    url_lower = url.lower()
    clean = url_lower.replace("https://", "").replace("http://", "").split("/")[0]
    parts = clean.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return clean or "unknown"

def add_gemini_key():
    print("\n--- Add Gemini Key ---")
    key = input("Enter Gemini API key: ").strip()
    if not key:
        print("Error: API key cannot be empty.")
        return

    data = load_keys()
    data["gemini"].append(key)
    if save_keys(data):
        print("Gemini API key added successfully!")

def add_openai_compatible_key():
    print("\n--- Add OpenAI-Compatible Key ---")
    provider = input("Enter provider name (e.g. groq, openrouter, nvidia): ").strip()
    if not provider:
        print("Error: Provider name cannot be empty.")
        return

    data = load_keys()
    existing_entry = None
    
    # Check if provider already exists in keys.json
    for entry in data["openai_compatible"]:
        if not isinstance(entry, dict):
            continue
        entry_provider = entry.get("provider", "").strip().lower()
        if entry_provider == provider.lower():
            existing_entry = entry
            break
        # Fallback substring match in URL if provider key is missing
        if not entry_provider and "base_url" in entry:
            extracted = get_provider_name_from_url(entry["base_url"])
            if extracted == provider.lower():
                existing_entry = entry
                break

    if existing_entry:
        base_url = existing_entry.get("base_url")
        model = existing_entry.get("model")
        print(f"Found existing configuration for provider '{provider}':")
        print(f"  Base URL: {base_url}")
        print(f"  Model:    {model}")
        key = input("Enter new API key: ").strip()
        if not key:
            print("Error: API key cannot be empty.")
            return
    else:
        base_url = input("Enter Base URL (e.g. https://api.groq.com/openai/v1): ").strip()
        if not base_url:
            print("Error: Base URL cannot be empty.")
            return
        model = input("Enter Model name (e.g. llama-3.3-70b-versatile): ").strip()
        if not model:
            print("Error: Model name cannot be empty.")
            return
        key = input("Enter API key: ").strip()
        if not key:
            print("Error: API key cannot be empty.")
            return

    new_entry = {
        "provider": provider,
        "key": key,
        "base_url": base_url,
        "model": model
    }
    data["openai_compatible"].append(new_entry)
    if save_keys(data):
        print(f"OpenAI-compatible key for '{provider}' added successfully!")

def view_keys():
    print("\n--- Current Keys Configured ---")
    data = load_keys()
    
    gemini_keys = data.get("gemini", [])
    print(f"Gemini Keys (Total: {len(gemini_keys)}):")
    if gemini_keys:
        for k in gemini_keys:
            print(f"  - {mask_key(k)}")
    else:
        print("  (No Gemini keys configured)")

    print()
    openai_keys = data.get("openai_compatible", [])
    
    # Group by provider
    groups = {}
    for entry in openai_keys:
        if not isinstance(entry, dict):
            continue
        p_name = entry.get("provider", "").strip()
        if not p_name and "base_url" in entry:
            p_name = get_provider_name_from_url(entry["base_url"]).capitalize()
        if not p_name:
            p_name = "Unknown Provider"
        
        # Normalize grouping key but preserve display case
        group_key = p_name.lower()
        if group_key not in groups:
            groups[group_key] = {"display_name": p_name, "entries": []}
        groups[group_key]["entries"].append(entry)

    print(f"OpenAI-Compatible Keys (Total entries: {len(openai_keys)}):")
    if groups:
        for group_key in sorted(groups.keys()):
            group = groups[group_key]
            entries = group["entries"]
            print(f"  Provider: {group['display_name']} (Total: {len(entries)})")
            for entry in entries:
                masked = mask_key(entry.get("key", ""))
                model = entry.get("model", "N/A")
                base_url = entry.get("base_url", "N/A")
                print(f"    - {masked} (Model: {model}, URL: {base_url})")
    else:
        print("  (No OpenAI-compatible keys configured)")
    print()

def main():
    while True:
        print("\n====================")
        print("API Key Setup Wizard")
        print("====================")
        print("[1] Add Gemini key")
        print("[2] Add OpenAI-compatible key")
        print("[3] View current keys (masked)")
        print("[4] Exit")
        
        try:
            choice = input("Select an option [1-4]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            sys.exit(0)

        if choice == "1":
            add_gemini_key()
        elif choice == "2":
            add_openai_compatible_key()
        elif choice == "3":
            view_keys()
        elif choice == "4":
            print("Exiting. Goodbye!")
            break
        else:
            print("Invalid option. Please enter a number between 1 and 4.")

if __name__ == "__main__":
    main()
