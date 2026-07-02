# Conductor Agent Data

This directory contains all data for the conductor agent:

- `raw/` - Raw exported conversation data from various platforms
- `processed/` - Standardized JSON conversations after processing
- `chroma_db/` - ChromaDB vector database persistence
- `embeddings_cache/` - Cached embeddings to avoid re-generation

## Directory Structure

```
data/
├── raw/
│   ├── chatgpt_conversations.json
│   ├── gemini_export/
│   ├── grok_export.zip
│   └── ...
├── processed/
│   ├── chatgpt_conversations.json
│   ├── gemini_conversations.json
│   ├── grok_conversations.json
│   ├── antigravity_conversations.json
│   └── *_code_snippets.json
├── chroma_db/
│   └── [ChromaDB internal files]
└── embeddings_cache/
    └── [Cached embedding files]
```

## Notes

- `.gitignore` excludes this directory to protect your private conversation data
- Vector database can be rebuilt by re-running ingestion
- Clear `embeddings_cache/` to force re-generation (will incur API costs)
