# shared/

Cross-cutting assets referenced by both backend and (where relevant) frontend.
Populated incrementally by later phases.

| Folder | Purpose | Phase |
|--------|---------|-------|
| `prompts/` | Versioned LLM prompt templates | 5, 8 |
| `workflows/` | FirstMed operational workflow definitions (source of truth mirrored from Notion) | 6 |
| `templates/` | Approved email templates with `{{placeholders}}` | 7 |
| `schemas/` | Shared JSON schemas / contracts | 4+ |
| `constants/` | Shared enums & constants (intents, roles, escalation reasons) | ongoing |
