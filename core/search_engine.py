#!/usr/bin/env python3
import os
import sys
import json
import re
import argparse
import requests

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", 
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being", 
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't", 
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", 
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", 
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", 
    "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", 
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", 
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", 
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", 
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", 
    "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", 
    "the", "their", "theirs", "them", "themselves", "then", "there", "there's", 
    "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", 
    "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", 
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", 
    "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", 
    "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", 
    "you're", "you've", "your", "yours", "yourself", "yourselves"
}

# Setup system path to import from core
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.key_manager import get_response as km_get_response

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

def tokenize(text):
    """Tokenize text into lowercase alphanumeric words, filtering stopwords."""
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return [w for w in words if w not in STOPWORDS]

def update_index_map_keywords(index_map_path, parts_to_update, query_tokens):
    """Updates keywords list of target parts in index_map.json."""
    if not query_tokens or not parts_to_update:
        return
        
    try:
        with open(index_map_path, "r", encoding="utf-8") as f:
            index_map = json.load(f)
            
        parts = index_map.get("parts", {})
        updated = False
        
        for part_key in parts_to_update:
            part_str = str(part_key)
            if part_str in parts:
                current_keywords = parts[part_str].setdefault("keywords", [])
                for token in query_tokens:
                    if token not in current_keywords:
                        current_keywords.append(token)
                        updated = True
                        
        if updated:
            with open(index_map_path, "w", encoding="utf-8") as f:
                json.dump(index_map, f, indent=2, ensure_ascii=False)
            print(f"Self-improvement: Updated keywords for parts {list(parts_to_update)} in index_map.json", file=sys.stderr)
    except Exception as e:
        print(f"Error updating index_map.json for self-improvement: {e}", file=sys.stderr)

def search_memory(query, is_mock=False, mock_target=1, memory_dir="memory"):
    """Searches memory using a two-phase strategy. Returns (matched_part, content)."""
    index_map_path = os.path.join(memory_dir, "indexes", "index_map.json")
    if not os.path.exists(index_map_path):
        print(f"Error: Index map file not found at {index_map_path}. Run chunker first.", file=sys.stderr)
        return None, ""

    try:
        with open(index_map_path, "r", encoding="utf-8") as f:
            index_map = json.load(f)
    except Exception as e:
        print(f"Error reading index map: {e}", file=sys.stderr)
        return None, ""

    total_parts = index_map.get("total_parts", 0)
    parts = index_map.get("parts", {})

    if total_parts <= 0 or not parts:
        print("Error: Index map contains no parts.", file=sys.stderr)
        return None, ""

    query = query.strip()
    if not query:
        print("Error: Query cannot be empty.", file=sys.stderr)
        return None, ""

    # Step 1.5: Query Intent Classification via Gemini Flash
    mock_decision = "YES"
    if is_mock:
        tokens = tokenize(query)
        if len(tokens) < 2 or any(token in ["hello", "hi", "hey", "greetings", "exit"] for token in tokens):
            mock_decision = "NO"

    intent_prompt = (
        "Does this message require searching past conversation history to answer properly? \n"
        "Reply ONLY with YES or NO.\n"
        f"Message: {query}"
    )
    
    decision = km_get_response(intent_prompt, is_mock=is_mock, mock_response=mock_decision)
    decision_clean = decision.strip().upper()
    if decision_clean.startswith("ALERT:"):
        print(decision_clean, file=sys.stderr)
        decision_clean = "NO"
        
    print(f"Intent search evaluation: {decision_clean}", file=sys.stderr)
    if "NO" in decision_clean:
        print("Query evaluated as NOT requiring memory. Skipping search.", file=sys.stderr)
        return None, ""

    query_tokens = tokenize(query)
    print(f"Query tokens: {query_tokens}", file=sys.stderr)

    # STEP 1: Reflection Search
    reflection_index_path = os.path.join(memory_dir, "indexes", "reflection_index.json")
    if os.path.exists(reflection_index_path):
        try:
            with open(reflection_index_path, "r", encoding="utf-8") as f:
                ref_index_data = json.load(f)
            
            reflections = ref_index_data.get("reflections", {})
            ref_candidates = []
            
            for ref_id, ref_entry in reflections.items():
                # Match keywords (weight = 3)
                ref_keywords = set(ref_entry.get("keywords", []))
                kw_matches = sum(1 for token in query_tokens if token in ref_keywords)
                
                # Match summary (weight = 1)
                summary_tokens = set(tokenize(ref_entry.get("summary", "")))
                sum_matches = sum(1 for token in query_tokens if token in summary_tokens)
                
                if kw_matches > 0 or sum_matches > 0:
                    importance = ref_entry.get("importance", 5)
                    score = (kw_matches * 3) + (sum_matches * 1) + (importance * 0.2)
                    ref_candidates.append((ref_id, score))
            
            if ref_candidates:
                ref_candidates.sort(key=lambda x: x[1], reverse=True)
                best_ref_id, best_score = ref_candidates[0]
                print(f"Reflection Search candidate: {best_ref_id} (score: {best_score})", file=sys.stderr)
                
                if best_score >= 3.0:
                    # Retrieve the reflection from its individual file
                    ref_filepath = os.path.join(memory_dir, "reflections", f"reflection_{best_ref_id}.json")
                    if os.path.exists(ref_filepath):
                        with open(ref_filepath, "r", encoding="utf-8") as f:
                            ref_data = json.load(f)
                        
                        goal = ref_data.get("goal", "")
                        outcome = ref_data.get("outcome", "")
                        success_val = ref_data.get("success", "")
                        failure_val = ref_data.get("failure", "")
                        lesson = ref_data.get("lesson", "")
                        
                        # Self-Improvement: increment retrieval count and learn phrasing keywords
                        ref_entry = reflections[str(best_ref_id)]
                        ref_entry["retrieval_count"] = ref_entry.get("retrieval_count", 0) + 1
                        
                        # Add matching query tokens to keywords list (learning common user phrasing)
                        learned_kws = list(ref_entry.get("keywords", []))
                        updated_keywords = False
                        for token in query_tokens:
                            if token not in learned_kws:
                                learned_kws.append(token)
                                updated_keywords = True
                        
                        if updated_keywords:
                            ref_entry["keywords"] = learned_kws
                            ref_data["keywords"] = learned_kws
                            # Save back the individual file
                            with open(ref_filepath, "w", encoding="utf-8") as f:
                                json.dump(ref_data, f, indent=2, ensure_ascii=False)
                        
                        # Save back the index map
                        with open(reflection_index_path, "w", encoding="utf-8") as f:
                            json.dump(ref_index_data, f, indent=2, ensure_ascii=False)
                            
                        print(f"Reflection Hit: Retrieved reflection {best_ref_id} directly. Self-improvement executed.", file=sys.stderr)
                        
                        formatted_reflection = (
                            "[Reflection Memory (Lesson Learned)]\n"
                            f"Goal: {goal}\n"
                            f"Outcome: {outcome}\n"
                            f"Success: {success_val}\n"
                            f"Failure: {failure_val}\n"
                            f"Lesson: {lesson}"
                        )
                        # Return None for part, and the reflection context
                        return None, formatted_reflection
        except Exception as e:
            print(f"Warning: Error during reflection search: {e}", file=sys.stderr)

    # PHASE 1: Keyword Match
    scored_parts = []
    for part_key, part_val in parts.items():
        # Score keywords matches (weight = 3)
        part_keywords = set()
        for kw in part_val.get("keywords", []):
            part_keywords.update(tokenize(kw))
        kw_matches = sum(1 for token in query_tokens if token in part_keywords)

        # Score summary matches (weight = 1)
        summary_tokens = tokenize(part_val.get("summary", ""))
        sum_matches = sum(1 for token in query_tokens if token in summary_tokens)

        score = (kw_matches * 3) + (sum_matches * 1)
        if score > 0:
            scored_parts.append((int(part_key), score))

    # Sort parts descending by score
    scored_parts.sort(key=lambda x: x[1], reverse=True)

    matched_part = None
    use_phase_2 = True

    if scored_parts:
        best_part, s1 = scored_parts[0]
        s2 = scored_parts[1][1] if len(scored_parts) > 1 else 0
        print(f"Phase 1 - Best candidate part: {best_part} (score: {s1}), Runner-up score: {s2}", file=sys.stderr)
        
        # Check if one part scores clearly higher (margin of at least 1 point)
        if s1 - s2 >= 1:
            matched_part = best_part
            use_phase_2 = False
            print(f"Phase 1 Hit: Confident match found at part {matched_part}.", file=sys.stderr)
        else:
            print("Phase 1 Tie/Near-equal: Fall through to Phase 2 Binary Search.", file=sys.stderr)

    # PHASE 2: Binary Search Fallback
    visited_parts = []
    if use_phase_2:
        print("Starting Phase 2 Binary Search...", file=sys.stderr)
        low = 1
        high = total_parts
        max_hops = 10
        hops = 0
        last_mid = None

        while low <= high:
            if hops >= max_hops:
                print(f"ALERT: Binary search exceeded maximum of {max_hops} hops.", file=sys.stderr)
                return None, f"ALERT: Search exceeded maximum binary search hops ({max_hops}) without converging."

            mid = (low + high) // 2
            last_mid = mid
            visited_parts.append(mid)
            hops += 1

            part_key = str(mid)
            if part_key not in parts:
                print(f"Error: Part {mid} summary missing in index map.", file=sys.stderr)
                break

            part_summary = parts[part_key].get("summary", "")
            print(f"Hop {hops}: Examining part {mid}...", file=sys.stderr)

            mock_direction = "BEFORE" if mid > mock_target else "AFTER"
            prompt = (
                "You are helping a search engine navigate a chronological conversation log.\n"
                f"User Query: {query}\n"
                f"Current Part Summary: {part_summary}\n\n"
                "Based on this summary, is the answer to this query BEFORE or AFTER this part chronologically?\n"
                "Reply ONLY with BEFORE or AFTER."
            )
            direction = km_get_response(prompt, is_mock=is_mock, mock_response=mock_direction)
            direction_clean = direction.strip().upper()
            if direction_clean.startswith("ALERT:"):
                print(direction_clean, file=sys.stderr)
                direction_clean = "BEFORE"
            print(f"Gemini response for part {mid}: {direction_clean}", file=sys.stderr)

            if "BEFORE" in direction_clean:
                high = mid - 1
            elif "AFTER" in direction_clean:
                low = mid + 1
            else:
                print(f"Warning: Ambiguous navigation choice '{direction_clean}'. Defaulting to BEFORE.", file=sys.stderr)
                high = mid - 1

        matched_part = last_mid
        print(f"Phase 2 Hit: Converged to part {matched_part} after {hops} hops. Visited: {visited_parts}", file=sys.stderr)

    # Retrieve and output the matched part file content
    part_filename = f"part_{matched_part}.txt"
    part_path = os.path.join(memory_dir, "chunks", part_filename)

    if not os.path.exists(part_path):
        print(f"Error: Chunk file {part_path} does not exist.", file=sys.stderr)
        return matched_part, ""

    try:
        with open(part_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading part content: {e}", file=sys.stderr)
        return matched_part, ""

    # AFTER RETRIEVAL: Self Improvement
    parts_to_update = set()
    if not use_phase_2:
        parts_to_update.add(matched_part)
    else:
        parts_to_update.add(matched_part)
        parts_to_update.update(visited_parts)

    update_index_map_keywords(index_map_path, parts_to_update, query_tokens)

    return matched_part, content

def get_response(query, is_mock=False, mock_target=1, memory_dir="memory"):
    """Alias for search_memory to match programmatic expectations."""
    return search_memory(query, is_mock=is_mock, mock_target=mock_target, memory_dir=memory_dir)

def main():
    parser = argparse.ArgumentParser(description="Search conversation memory.")
    parser.add_argument("query", help="User search query string.")
    parser.add_argument("--api-key", help="Gemini API key (ignored, handled by key_manager).")
    parser.add_argument("--memory-dir", default="memory", help="Directory where memory files are located (default: 'memory').")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (does not call the Gemini API, uses mock binary search directions).")
    parser.add_argument("--mock-target", type=int, default=1, help="Target part number for mock binary search navigation (default: 1).")
    args = parser.parse_args()

    load_env_file()

    matched_part, content = search_memory(args.query, is_mock=args.mock, mock_target=args.mock_target, memory_dir=args.memory_dir)
    if matched_part is not None:
        print(f"=== Part Number: {matched_part} ===")
        print(content)

if __name__ == "__main__":
    main()
