#!/usr/bin/env python3
import os
import sys
import json
import datetime
import argparse
import requests

# Setup system path to import from core
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.key_manager import get_response
from core.search_engine import tokenize

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

def get_subdirs(output_dir):
    chunks_dir = os.path.join(output_dir, "chunks")
    reflections_dir = os.path.join(output_dir, "reflections")
    indexes_dir = os.path.join(output_dir, "indexes")
    
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(reflections_dir, exist_ok=True)
    os.makedirs(indexes_dir, exist_ok=True)
    
    return chunks_dir, reflections_dir, indexes_dir

def should_reflect_heuristic(summary, chunk_content):
    # Heuristics filter:
    # 1. Must have at least 2 user turns in the chunk.
    user_turns = [line for line in chunk_content.splitlines() if line.strip().startswith("User:")]
    if len(user_turns) < 2:
        return False

    # 2. Must contain project planning, debugging, business decisions, agent dev, or problem solving keywords
    combined = (summary + " " + chunk_content).lower()
    keywords = [
        "plan", "project", "task", "outreach", "strategy", "todo", "milestone", # project planning
        "debug", "error", "bug", "fix", "code", "test", "build", "exception", "compile", # technical/agent dev
        "price", "pricing", "business", "market", "decision", "client", "revenue", # business decisions
        "solved", "resolved", "solution", "working", "correct" # problem solving
    ]
    return any(kw in combined for kw in keywords)

def chunk_log_file(filepath, is_mock=False, output_dir="memory", append=False):
    """Chunks a conversation log file and summarizes parts using Gemini Flash."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            log_content = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}", file=sys.stderr)
        return False

    if not log_content.strip():
        print(f"Error: Conversation log at {filepath} is empty.", file=sys.stderr)
        return False

    # Chunking logic
    # Token estimation: 1 token ≈ 4 characters
    # Max tokens per chunk: 4000
    # Max character length: 16000
    lines = log_content.splitlines(keepends=True)
    chunks = []
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line)
        if current_len + line_len > 16000 and current_len > 0:
            chunks.append("".join(current_chunk))
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        chunks.append("".join(current_chunk))

    new_parts_count = len(chunks)
    print(f"Total parts generated from chunker: {new_parts_count}", file=sys.stderr)

    chunks_dir, reflections_dir, indexes_dir = get_subdirs(output_dir)

    index_map_path = os.path.join(indexes_dir, "index_map.json")
    
    # Load existing map
    existing_map = {}
    if os.path.exists(index_map_path):
        try:
            with open(index_map_path, "r", encoding="utf-8") as f:
                existing_map = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read existing index_map.json: {e}", file=sys.stderr)

    existing_parts = existing_map.get("parts", {})
    existing_total_parts = existing_map.get("total_parts", 0)

    # Determine starting index for new parts
    start_idx = (existing_total_parts + 1) if append else 1

    parts_dict = {}
    if append:
        # Carry over existing parts
        parts_dict.update(existing_parts)

    for i, chunk in enumerate(chunks):
        part_idx = start_idx + i
        part_filename = f"part_{part_idx}.txt"
        part_path = os.path.join(chunks_dir, part_filename)

        # Write chunk to file
        with open(part_path, "w", encoding="utf-8") as f:
            f.write(chunk)
        print(f"Saved chunk {part_idx} to {part_path}", file=sys.stderr)

        # Get summary
        print(f"Summarizing chunk {part_idx}...", file=sys.stderr)
        words = chunk.split()
        snippet = " ".join(words[:10])
        mock_summary = f"Mock Summary: This part discusses {snippet}..."
        
        prompt = (
            "Write ONE descriptive sentence summarizing this part of a conversation log. "
            "Do not include any preamble, markdown, or extra commentary. "
            "Output only the single sentence.\n\n"
            f"{chunk}"
        )
        summary = get_response(prompt, is_mock=is_mock, mock_response=mock_summary)
        if summary.startswith("ALERT:"):
            print(summary, file=sys.stderr)

        # Timestamp in ISO 8601 format
        timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()

        # Preserve keywords if they already exist (only relevant if overwriting/not appending)
        part_key = str(part_idx)
        existing_keywords = existing_parts.get(part_key, {}).get("keywords", [])

        # Extract 3-5 key terms from summary using tokenization, preserving order
        summary_tokens = tokenize(summary)
        unique_tokens = []
        for token in summary_tokens:
            if token not in unique_tokens:
                unique_tokens.append(token)
        extracted_keywords = unique_tokens[:5]

        # Merge new keywords preserving order
        merged_keywords = list(existing_keywords)
        for kw in extracted_keywords:
            if kw not in merged_keywords:
                merged_keywords.append(kw)

        parts_dict[part_key] = {
            "summary": summary,
            "keywords": merged_keywords,
            "timestamp": timestamp
        }

        # Check heuristics before generating reflection
        if should_reflect_heuristic(summary, chunk):
            print(f"Heuristics passed for chunk {part_idx}. Generating reflection...", file=sys.stderr)
            reflection_index_path = os.path.join(indexes_dir, "reflection_index.json")
            existing_reflections = {}
            if os.path.exists(reflection_index_path):
                try:
                    with open(reflection_index_path, "r", encoding="utf-8") as f:
                        ref_data = json.load(f)
                        existing_reflections = ref_data.get("reflections", {})
                except Exception as e:
                    print(f"Warning: Could not read reflection_index.json: {e}", file=sys.stderr)
            
            if existing_reflections:
                ref_id = max(int(k) for k in existing_reflections.keys()) + 1
            else:
                ref_id = 1
                
            mock_ref_text = (
                "Goal: Mock Goal outreach\n"
                "Outcome: Mock Outcome completed\n"
                "Success: Mock Success pricing identified\n"
                "Failure: Mock Failure no lead source\n"
                "Lesson: Lead acquisition decided before pricing discussions.\n"
                "Importance: 8"
            )
            
            ref_prompt = (
                "Write a highly compressed reflection from the following segment summary and details.\n"
                "Do not write long reflective essays. Keep the entire response extremely short and concise (100-300 characters total).\n"
                "If the segment is not meaningful for learning lessons, respond with 'SKIP'.\n\n"
                f"Summary: {summary}\n"
                f"Details:\n{chunk}\n\n"
                "Format your response exactly as follows:\n"
                "Goal: <short goal description>\n"
                "Outcome: <short outcome description>\n"
                "Success: <what worked well>\n"
                "Failure: <what failed/what was missing>\n"
                "Lesson: <core lesson learned for future decisions>\n"
                "Importance: <importance score from 1 to 10>\n"
            )
            
            ref_text = get_response(ref_prompt, is_mock=is_mock, mock_response=mock_ref_text)
            
            if ref_text and "SKIP" not in ref_text.upper() and not ref_text.startswith("ALERT:"):
                goal = ""
                outcome = ""
                success_val = ""
                failure_val = ""
                lesson = ""
                importance_val = 5
                
                for line in ref_text.splitlines():
                    line = line.strip()
                    if line.startswith("Goal:"):
                        goal = line.replace("Goal:", "", 1).strip()
                    elif line.startswith("Outcome:"):
                        outcome = line.replace("Outcome:", "", 1).strip()
                    elif line.startswith("Success:"):
                        success_val = line.replace("Success:", "", 1).strip()
                    elif line.startswith("Failure:"):
                        failure_val = line.replace("Failure:", "", 1).strip()
                    elif line.startswith("Lesson:"):
                        lesson = line.replace("Lesson:", "", 1).strip()
                    elif line.startswith("Importance:"):
                        imp_str = line.replace("Importance:", "", 1).strip()
                        try:
                            importance_val = int(imp_str)
                        except ValueError:
                            importance_val = 5
                            
                if goal or lesson:
                    ref_keywords = []
                    for t in tokenize(goal + " " + lesson):
                        if t not in ref_keywords:
                            ref_keywords.append(t)
                            
                    ref_filename = f"reflection_{ref_id}.json"
                    ref_filepath = os.path.join(reflections_dir, ref_filename)
                    relative_ref_path = f"memory/reflections/{ref_filename}"
                    
                    reflection_payload = {
                        "id": ref_id,
                        "timestamp": timestamp,
                        "goal": goal,
                        "outcome": outcome,
                        "success": success_val,
                        "failure": failure_val,
                        "lesson": lesson,
                        "keywords": ref_keywords,
                        "importance_score": importance_val
                    }
                    
                    try:
                        with open(ref_filepath, "w", encoding="utf-8") as f:
                            json.dump(reflection_payload, f, indent=2, ensure_ascii=False)
                        print(f"Saved reflection {ref_id} to {ref_filepath}", file=sys.stderr)
                        
                        ref_summary = f"Goal: {goal}. Outcome: {outcome}. Lesson: {lesson}"
                        existing_reflections[str(ref_id)] = {
                            "summary": ref_summary,
                            "keywords": ref_keywords,
                            "importance": importance_val,
                            "timestamp": timestamp,
                            "retrieval_count": 0,
                            "file_path": relative_ref_path
                        }
                        
                        with open(reflection_index_path, "w", encoding="utf-8") as f:
                            json.dump({"reflections": existing_reflections}, f, indent=2, ensure_ascii=False)
                        print(f"Updated reflection index with reflection {ref_id}", file=sys.stderr)
                    except Exception as e:
                        print(f"Error saving reflection: {e}", file=sys.stderr)

    # Construct the final index map
    new_map = {
        "total_parts": len(parts_dict),
        "parts": parts_dict
    }

    with open(index_map_path, "w", encoding="utf-8") as f:
        json.dump(new_map, f, indent=2, ensure_ascii=False)
    print(f"Saved index map to {index_map_path}", file=sys.stderr)
    return True

def main():
    parser = argparse.ArgumentParser(description="Chunk a conversation log and summarize parts using Gemini Flash.")
    parser.add_argument("log_file", nargs="?", help="Path to the conversation log file. If omitted, reads from stdin.")
    parser.add_argument("--api-key", help="Gemini API key (ignored, handled by key_manager).")
    parser.add_argument("--output-dir", default="memory", help="Directory where chunks and index_map.json will be saved (default: 'memory').")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (does not call the Gemini API, generates mock summaries).")
    parser.add_argument("--append", action="store_true", help="Append new parts instead of overwriting.")
    args = parser.parse_args()

    # Load env file first
    load_env_file()

    # Read log content
    if args.log_file:
        chunk_log_file(args.log_file, is_mock=args.mock, output_dir=args.output_dir, append=args.append)
    else:
        print("Reading conversation log from standard input...", file=sys.stderr)
        log_content = sys.stdin.read()
        os.makedirs(args.output_dir, exist_ok=True)
        temp_filepath = os.path.join(args.output_dir, "temp_log.txt")
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(log_content)
        chunk_log_file(temp_filepath, is_mock=args.mock, output_dir=args.output_dir, append=args.append)
        try:
            os.remove(temp_filepath)
        except Exception:
            pass

if __name__ == "__main__":
    main()
