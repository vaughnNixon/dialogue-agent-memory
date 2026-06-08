# Athena: Dialogue Agent with Long-Term Memory (V2)

Athena is a terminal-based chat agent that implements an advanced long-term memory architecture and a universal, rotating API provider pool. It supports automatic conversation log chunking, intent-based memory search, self-improving keyword indexing, failover API endpoint rotation, and a lightweight structured **Reflection Memory** system.

---

## Architecture Overview

```mermaid
graph TD
    User([User Input]) --> Agent[core/agent.py]
    Agent --> IntentCheck{Search Needed? <br> core/search_engine.py}
    
    IntentCheck -- NO --> GenerateResponse[Direct Prompt Response]
    IntentCheck -- YES --> ReflectionSearch{Reflection Match? <br> score >= 3}
    
    ReflectionSearch -- YES --> GenerateResponse[Direct Reflection Context Response]
    ReflectionSearch -- NO --> Phase1{Phase 1: Keyword Match}
    
    Phase1 -- Confident Margin >= 1 --> RetrievePart[Retrieve Part Content]
    Phase1 -- Weak/No Match --> Phase2[Phase 2: Chronological Binary Search]
    
    Phase2 --> RetrievePart
    RetrievePart --> GenerateResponse
    
    GenerateResponse --> LogHistory[Log Chat to history]
    LogHistory --> AutoChunk{History > 16KB?}
    AutoChunk -- YES --> Chunker[memory/chunker.py]
    Chunker -- Summarize & Extract Keywords --> Index[memory/indexes/index_map.json]
    Chunker -- Run Heuristics & Generate Reflection --> ReflectionIndex[memory/indexes/reflection_index.json]
    
    subgraph Provider Pool [core/key_manager.py]
        Gemini[Gemini Flash]
        OpenAIComp[OpenAI-Compatible Pool]
    end
    
    GenerateResponse -. Rotating Requests .-> ProviderPool
```

The system operates across three core divisions:
1. **Dialogue Agent (`core/agent.py`)**: Manages the interactive prompt, records exchange logs, and automatically chunks memory once size limits are reached.
2. **Memory Architecture (`memory/chunker.py` & `core/search_engine.py`)**: Partitions conversation history, extracts keywords, and implements a multi-stage retrieval lookup:
   - **Reflection Search**: Checks for lightweight, high-value lesson summaries prior to looking up raw text chunks.
   - **Phase 1 (Keyword Match)**: Fast keyword overlap check with a confidence margin.
   - **Phase 2 (Binary Search)**: Narrowing down chronological segments using directional queries (BEFORE / AFTER).
   - **Self-Improvement**: Retrospective queries dynamically update key indices and learn phrasing.
3. **Rotating Provider Pool (`core/key_manager.py`)**: Cycles through multiple Gemini and OpenAI-compatible API keys to tolerate rate-limiting and connection issues.

---

## Example Retrieval Flow

Athena retrieves memory using a structured cascading order. If high-level lessons (reflections) or high-confidence keyword matches are found, it skips full database lookups to optimize token consumption.

```
User Query
     ↓
Intent Check
     ↓
Reflection Search (score >= 3.0)
   /    \
 yes    no
  ↓      ↓
Return  Keyword Match
Context    ↓
        Confident? (Margin >= 1)
         /    \
       yes    no
        ↓      ↓
      Return  Binary Search
      Context      ↓
                Retrieve
```

---

## Repository Structure

```
athena/
├── core/
│   ├── agent.py          # Terminal dialogue loop and auto-chunk scheduler
│   ├── key_manager.py    # Rotation, HTTP payloads, and error count management
│   ├── search_engine.py  # Two-phase memory retrieval and keyword tokenization
│   └── setup_keys.py     # Interactive CLI setup wizard for API keys
├── memory/
│   ├── chunks/           # Git-ignored raw conversation segments (part_N.txt)
│   ├── reflections/      # Git-ignored parsed reflection JSON objects (reflection_N.json)
│   ├── indexes/          # Git-ignored maps (index_map.json, reflection_index.json)
│   └── chunker.py        # Dialogue log segmenter & reflection generator
├── README.md             # Project documentation
└── requirements.txt      # Dependency configurations
```

---

## Module Reference

### 1. Universal Rotating Provider Pool (`core/key_manager.py`)
- Exposes a unified `get_response(prompt)` function.
- Parses a mix of Gemini keys and OpenAI-compatible endpoints (e.g. Groq, OpenRouter, Nvidia NIM) in a unified pool.
- Standardizes OpenAI completions using `{base_url}/chat/completions` with Bearer auth.
- Rotates endpoints on failure. Enforces a strict cap of 3 consecutive failures to safeguard usage, resetting the error count to zero upon any successful API call.

### 2. API Key Setup Wizard (`core/setup_keys.py`)
An interactive CLI helper wizard. Launch it using:
```powershell
python core/setup_keys.py
```
- **Option 1**: Appends Gemini keys directly.
- **Option 2**: Adds OpenAI-compatible keys. If the provider name exists (e.g. `groq`), it auto-fills existing `base_url` and `model` configuration to save typing.
- **Option 3**: Lists configured keys in a masked format (e.g. `...Ot4A`) grouped by provider.

### 3. Dialogue Agent (`core/agent.py`)
Runs the dialogue loop.
- Records all User/Agent exchanges in a temporary chat log (`memory/chat_history.txt`).
- When the log exceeds 16,000 characters (~4,000 tokens), it automatically compiles, summarizes, extracts key terms, and appends the log to the chronological archives (`memory/chunks/part_N.txt`).

### 4. Memory Search Engine (`core/search_engine.py`)
Retrieves relevant context matching queries.
- **Intent Check**: Submits queries to the model first to decide if historical context is required (skips lookup for small talk/greetings).
- **Reflection Search**: Checks `memory/indexes/reflection_index.json` to match query tokens against parsed reflection keywords and summaries.
- **Phase 1 (Keyword Search)**: Ranks conversation parts based on keyword/summary matches. If the best candidate part wins by a margin of $\ge 1$ point, it returns that part.
- **Phase 2 (Binary Search)**: If Phase 1 cannot determine a clear winner, it performs binary search, prompting the model to navigate BEFORE or AFTER a midpoint part chronologically.
- **Self-Improvement**: Retrospective query tokens are appended to that part's `"keywords"` index in `index_map.json` to optimize future Phase 1 matches.

### 5. Reflection Memory Subsystem (`memory/chunker.py`)
Extracts and indexes lesson summaries from conversation segments.
- **Heuristic Triggers**: Reflection generation only executes when a segment has at least 2 user turns and contains planning, debugging, business, or problem-solving keywords (skips greetings and jokes).
- **Reflection Format**: Generates a brief representation (100-300 characters) containing: Goal, Outcome, Success, Failure, Lesson, and Importance (1-10).
- **Phrase Learning**: When a reflection is retrieved, the query tokens are dynamically added to the reflection's keyword index. The retrieval count is also tracked.

---

## Future Roadmap

- [x] Reflection Memory System
- [x] Importance-based Scoring
- [ ] Client Namespaces & Segment Isolation
- [ ] Dense Semantic / Embedding Search
- [ ] Puter Cloud Service Integration
- [ ] Gradio Web interface
- [ ] HuggingFace Spaces Deployment

---

## Setup & Usage

### 1. Initialize API Keys
Run the interactive setup wizard:
```powershell
python core/setup_keys.py
```
Add your Gemini and OpenAI-compatible keys (such as Groq).

### 2. Install Dependencies
Install packages listed in `requirements.txt`:
```powershell
pip install -r requirements.txt
```

### 3. Launch Dialogue Loop
Start interacting with the agent:
```powershell
python core/agent.py
```
To run in offline dry-run (mock) mode:
```powershell
python core/agent.py --mock
```
To exit, type `exit`.
