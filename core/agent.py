#!/usr/bin/env python3
import os
import sys
import argparse

# Setup system path to import from core
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.key_manager import get_response
from core.search_engine import search_memory
from memory.chunker import chunk_log_file

def start_chat(is_mock=False, mock_target=1):
    """Enters a terminal dialogue loop that logs interactions and chunks memory."""
    print("Welcome to terminal chat loop. Type 'exit' to quit.\n", file=sys.stderr)
    
    # Ensure memory directory exists
    memory_dir = "memory"
    os.makedirs(memory_dir, exist_ok=True)
    history_path = os.path.join(memory_dir, "chat_history.txt")

    while True:
        try:
            user_input = input("User: ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...", file=sys.stderr)
            break

        if user_input.strip() == "exit":
            print("Exiting...", file=sys.stderr)
            break

        if not user_input.strip():
            continue

        # Step 2: Retrieve relevant memory
        part_num, context_content = search_memory(user_input, is_mock=is_mock, mock_target=mock_target, memory_dir=memory_dir)

        # Step 3: Call Gemini Flash (Pro is requested by user, but they explicitly told us to:
        # "Use the same key_manager get_response() for all Gemini calls.")
        prompt = (
            "You are an assistant. Answer the user's query utilizing the context below (if available).\n"
            "Context from past conversation segments:\n"
            "---"
            f"{context_content}"
            "---"
            f"User Query: {user_input}\n\n"
            "Provide a helpful, direct response."
        )

        if part_num is None:
            if context_content:
                mock_agent_response = f"[Mock Agent Response] Retrieved reflection memory. Prompt: {user_input}"
            else:
                mock_agent_response = f"[Mock Agent Response] Direct response (no memory retrieval). Prompt: {user_input}"
        else:
            mock_agent_response = f"[Mock Agent Response] Retrieved context from Part {part_num}. Prompt: {user_input}"
        
        response = get_response(prompt, is_mock=is_mock, mock_response=mock_agent_response)

        # Step 4: Print the response
        print(f"Agent: {response}")

        # Step 5: Log interaction
        try:
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(f"User: {user_input}\n")
                f.write(f"Agent: {response}\n\n")
        except Exception as e:
            print(f"Error logging conversation: {e}", file=sys.stderr)

        # Step 6: Check size and chunk if exceeds 16,000 characters
        try:
            if os.path.exists(history_path) and os.path.getsize(history_path) > 16000:
                print("\n[System Alert] Conversation history exceeds 16,000 characters. Automatically archiving to memory...", file=sys.stderr)
                # Call chunker with append=True to add to existing parts incrementally
                success = chunk_log_file(history_path, is_mock=is_mock, output_dir=memory_dir, append=True)
                if success:
                    # Truncate the history file to 0 bytes
                    with open(history_path, "w", encoding="utf-8") as f:
                        f.truncate(0)
                    print("[System Alert] Memory archived and chat history cleared.\n", file=sys.stderr)
        except Exception as e:
            print(f"Error during auto-chunking: {e}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Terminal chat agent with long-term memory.")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (dry-run, offline summaries and mock responses).")
    parser.add_argument("--mock-target", type=int, default=1, help="Target part number for mock binary search navigation (default: 1).")
    args = parser.parse_args()

    start_chat(is_mock=args.mock, mock_target=args.mock_target)

if __name__ == "__main__":
    main()
