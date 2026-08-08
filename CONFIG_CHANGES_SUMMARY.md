# Configuration Changes Summary

## What Was Changed

### 1. **backend/app/ai/client.py** (Main Fix)
- ✅ **Removed hardcoded Groq override** that was forcing Claude models to use Groq
- ✅ **Added multi-provider support** with proper Claude/Groq detection
- ✅ **Implemented auto-detection logic** based on model name:
  - `claude-*` → Uses `AsyncAnthropic` client
  - `llama-*/mixtral-*` → Uses OpenAI-compatible Groq client
- ✅ **Updated API key loading** to read correct key for each provider

### 2. **backend/app/core/config.py** (Optional Enhancement)
- ✅ **Changed default model** from `llama-3.3-70b-versatile` to `claude-3-5-sonnet-20241022`
- ✅ **Added documentation** explaining provider support
- ✅ **No breaking changes** - environment variables still override defaults

---

## Key Configuration Fields

### AI Settings (in `config.py` and `.env`)

```python
# backend/app/core/config.py (defaults)
groq_api_key: SecretStr = SecretStr("")
anthropic_api_key: SecretStr = SecretStr("")
ai_model: str = "claude-3-5-sonnet-20241022"
ai_max_tokens: int = 4096
anthropic_baa_signed: bool = False
```

### Required Environment Variables

For **Claude**:
```env
ANTHROPIC_API_KEY=sk-ant-api03-...
AI_MODEL=claude-3-5-sonnet-20241022  # or claude-haiku-4-5
```

For **Groq**:
```env
GROQ_API_KEY=gsk_...
AI_MODEL=llama-3.3-70b-versatile
```

---

## How Configuration Works

### Provider Selection Flow

```
┌─────────────────────────────────────────────────────┐
│ Read AI_MODEL from environment or config.py         │
│ (default: claude-3-5-sonnet-20241022)               │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│ AIClient.__init__() checks model name               │
└──────────────────────┬──────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
      Starts with          Starts with
      "claude"             "llama"/"mixtral"
           │                       │
           ▼                       ▼
    ┌────────────────┐    ┌────────────────┐
    │   Anthropic    │    │     Groq       │
    │   Provider     │    │    Provider    │
    └────────────────┘    └────────────────┘
           │                       │
           ▼                       ▼
    Load from              Load from
    ANTHROPIC_API_KEY      GROQ_API_KEY
```

---

## What You DON'T Need to Change

✅ **No changes needed to:**
- `backend/app/api/ai/__init__.py` (uses AIClient as-is)
- `backend/app/services/triage_service.py` (uses AIClient as-is)
- `backend/app/services/draft_service.py` (uses AIClient as-is)
- `.env` file structure (your existing keys still work)
- Database or other configs

---

## Backward Compatibility

✅ **Everything is backward compatible:**
- If you have `GROQ_API_KEY` set and `AI_MODEL=llama-3.3-70b-versatile`, it still works
- If you have `ANTHROPIC_API_KEY` set and `AI_MODEL=claude-*`, it now works (was broken before)
- If both keys are set, the one matching your `AI_MODEL` is used

---

## Production Deployment

### Important: anthropic_baa_signed

If deploying to production with real patient data:

```env
ENVIRONMENT=production
ANTHROPIC_BAA_SIGNED=true  # REQUIRED when using Anthropic in production
```

This indicates you've signed Anthropic's BAA (Business Associate Agreement) for HIPAA compliance.

**config.py enforces this:**
```python
if self.anthropic_api_key.get_secret_value() and not self.anthropic_baa_signed:
    raise ValueError("ANTHROPIC_BAA_SIGNED must be true before processing real patient data...")
```

---

## Testing Configuration

### Quick Test Script

```python
from app.core.config import settings
from app.ai.client import AIClient

# Check settings
print(f"AI Model: {settings.ai_model}")
print(f"Anthropic Key Set: {bool(settings.anthropic_api_key.get_secret_value())}")
print(f"Groq Key Set: {bool(settings.groq_api_key.get_secret_value())}")

# Check client
client = AIClient()
print(f"Provider: {client.provider}")
print(f"Model: {client.model}")
print(f"Configured: {client.configured}")
```

### Expected Output (with your current `.env`)
```
AI Model: claude-haiku-4-5
Anthropic Key Set: True
Groq Key Set: False
Provider: anthropic
Model: claude-haiku-4-5
Configured: True
```

---

## Summary

| File | Change | Impact |
|------|--------|--------|
| `client.py` | Removed Groq override, added provider detection | 🔴 Critical Fix |
| `config.py` | Default model changed, docs added | 🟡 Minor Enhancement |
| `.env` | No changes needed | ✅ Works as-is |

**Status: Ready to use Claude with proper confidence scoring! 🎉**
