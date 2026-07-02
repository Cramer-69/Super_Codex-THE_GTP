# Quick Start Guide

## 🚀 3-Minute Setup

### 1. Configure Your API Key
```powershell
cd "c:\Users\jjc29\antigravity agent 1\conductor_agent"
copy .env.example .env
notepad .env
```

Add your OpenAI API key:
```
OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. Ingest Your Antigravity Conversations
```powershell
python ingest.py
```

Wait for processing... ☕ (first run takes ~5-10 minutes)

### 3. Start Chatting!
```powershell
python -m cli.interactive
```

## 📝 Example Commands

```
You: What projects have I worked on?
You: /code async patterns
You: /platform antigravity conductor agent
You: /stats
You: /help
You: /exit
```

## 🎯 Add More Platforms

### Export ChatGPT
1. Go to chat.openai.com → Settings → Data Controls
2. Click "Export Data" and wait for email
3. Download and extract `conversations.json`
4. Run: `python ingest.py --chatgpt "path/to/conversations.json"`

### Export Gemini
1. Visit [Google Takeout](https://takeout.google.com)
2. Select "Gemini Apps Activity"
3. Download and extract
4. Run: `python ingest.py --gemini "path/to/gemini_export"`

### Export Grok
1. Export from Grok settings (ZIP format)
2. Run: `python ingest.py --grok "path/to/grok_export.zip"`

## 🔧 Troubleshooting

**No results found?**
- Run `/stats` to check if database has data
- Make sure you ran `python ingest.py` first

**API errors?**
- Check your `.env` file has the correct `OPENAI_API_KEY`
- Verify the key starts with `sk-`

**Installation issues?**
- Ensure Python 3.9+ is installed
- Run `pip install -r requirements.txt` again

## 📖 Full Documentation

See [README.md](file:///c:/Users/jjc29/antigravity%20agent%201/conductor_agent/README.md) for complete documentation.

## ✨ You're All Set!

Your conductor agent is ready to supercharge your AI workflow! 🎉
