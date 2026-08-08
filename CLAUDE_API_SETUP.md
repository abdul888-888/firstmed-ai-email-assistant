# Claude API Integration - Setup Guide

## Overview
The bug has been fixed! Your project now properly supports Claude (Anthropic) as the primary AI provider. Groq remains as an alternative option.

## Where to Add/Replace Your Claude API Key

### Option 1: Environment File (Recommended for Development)

**File Location:**
```
backend/.env
```

**Add or replace this line:**
```env
ANTHROPIC_API_KEY=your-actual-claude-api-key-here
```

**Example:**
```env
ANTHROPIC_API_KEY=sk-ant-api03-abc123xyz...
AI_MODEL=claude-3-5-sonnet-20241022
```

The `.env` file is already in your `.gitignore`, so your API key won't be committed to Git.

---

### Option 2: Environment Variables (Production/Server)

Set these environment variables on your system:

**On Windows (PowerShell):**
```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-api03-abc123xyz...", "User")
[Environment]::SetEnvironmentVariable("AI_MODEL", "claude-3-5-sonnet-20241022", "User")
```

**On Linux/Mac:**
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-abc123xyz...
export AI_MODEL=claude-3-5-sonnet-20241022
```

**Then restart your application.**

---

### Option 3: Docker/Deployment

In your `docker-compose.yml` or deployment config:

```yaml
services:
  backend:
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      AI_MODEL: claude-3-5-sonnet-20241022
```

---

## Configuration Details

### Available Settings

| Setting | Value | Purpose |
|---------|-------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Authenticates with Claude API |
| `AI_MODEL` | `claude-3-5-sonnet-20241022` | Specifies which Claude model to use |
| `AI_MODEL` | `claude-haiku-4-5` | Faster, cheaper alternative |
| `AI_MAX_TOKENS` | `4096` (default) | Max tokens for responses |

### Recommended Models

- **`claude-3-5-sonnet-20241022`** (Default in code)
  - Best balance of speed, accuracy, and cost
  - Ideal for medical triage and draft generation
  
- **`claude-haiku-4-5`** (Current in your `.env`)
  - Faster and cheaper
  - Good for less complex tasks
  
- **`claude-opus-4-1`**
  - Most capable (highest cost)
  - Use only if needed for complex reasoning

---

## Fallback to Groq (Alternative)

If you want to use Groq instead, set these variables:

```env
GROQ_API_KEY=your-groq-api-key-here
AI_MODEL=llama-3.3-70b-versatile
```

**The system will auto-detect:** If `AI_MODEL` starts with `claude`, it uses Claude. If it starts with `llama`, it uses Groq.

---

## How the Auto-Detection Works

Your updated `AIClient` now automatically:

1. **Reads `AI_MODEL`** from environment
2. **Detects provider:**
   - If model name starts with `claude` → Uses Anthropic API
   - If model name starts with `llama`/`mixtral` → Uses Groq API
3. **Loads the correct API key:**
   - Anthropic: `ANTHROPIC_API_KEY`
   - Groq: `GROQ_API_KEY`

---

## Testing Your Setup

### 1. Verify API Key is Loaded

```python
from app.ai.client import AIClient
client = AIClient()
print(f"Provider: {client.provider}")
print(f"Model: {client.model}")
print(f"Configured: {client.configured}")
```

### 2. Test Triage Classification

```bash
curl -X POST http://localhost:8000/api/v1/ai/triage \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "I need to schedule an appointment",
    "body": "Can I book a visit for next Tuesday?"
  }'
```

Expected response should include `confidence` > 0.70 for routine admin requests.

---

## Troubleshooting

### Error: "ANTHROPIC_API_KEY is not configured"

**Solution:**
1. Verify your `.env` file contains: `ANTHROPIC_API_KEY=sk-ant-api03-...`
2. Restart your application
3. Check that the file is in `backend/.env` (not `backend/app/.env`)

### Error: "Invalid API key"

**Solution:**
1. Double-check your API key from [console.anthropic.com](https://console.anthropic.com)
2. Ensure no extra spaces or line breaks around the key
3. Confirm the key hasn't expired

### Low confidence scores (< 0.70)

**This means:**
- Groq's old configuration is still running
- Or the triage model needs the correct API key
- **Solution:** Verify `ANTHROPIC_API_KEY` is set and restart the app

### "anthropic" module not found

**Solution:**
```bash
cd backend
pip install anthropic
```

---

## Current Configuration (In Your `.env`)

Your API key is already set in the `.env` file (which is in `.gitignore` and never committed).

✅ **Configuration is complete!** Just verify drafts are generating with higher confidence now.

---

## What Changed

### Before (Broken)
```python
# This FORCED Groq even with Claude API key set
if self.model.startswith("claude"):
    self.model = DEFAULT_GROQ_MODEL  # BUG! Overrode user choice
```

### After (Fixed)
```python
# Now properly respects Claude models
if self.provider == "anthropic":
    self._client = AsyncAnthropic(api_key=self._api_key)
elif self.provider == "groq":
    self._client = AsyncOpenAI(api_key=self._api_key, ...)
```

---

## Next Steps

1. ✅ Update is complete - Claude is now properly integrated
2. Test with a sample email to verify higher confidence scores
3. Monitor draft generation - should now work for routine admin emails
4. If cost is a concern, consider using `claude-haiku-4-5` (already in your `.env`)
