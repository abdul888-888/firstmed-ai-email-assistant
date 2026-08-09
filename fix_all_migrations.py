#!/usr/bin/env python3
"""Fix all migration revision IDs to use numeric format."""

import re
from pathlib import Path

migrations_dir = Path("backend/migrations/versions")

# Mapping of old revision names to new numeric IDs
fixes = [
    ("0001_initial", "0001", None, None),
    ("0002_google_credentials", "0002", "0001_initial", "0001"),
    ("0003_documents", "0003", "0002_google_credentials", "0002"),
    ("0004_draft_reviews", "0004", "0003_documents", "0003"),
    ("0005_review_actions", "0005", "0004_draft_reviews", "0004"),
    ("0006_document_embeddings", "0006", "0005_review_actions", "0005"),
    ("0007_templates", "0007", "0006_document_embeddings", "0006"),
    ("0008_pgvector_embeddings", "0008", "0007_templates", "0007"),
]

for old_rev, new_rev, old_down, new_down in fixes:
    file_path = migrations_dir / f"{new_rev}_{old_rev.split('_', 1)[1]}.py"
    if not file_path.exists():
        print(f"⚠️  File not found: {file_path}")
        continue
    
    content = file_path.read_text()
    
    # Replace revision ID
    content = re.sub(
        f'revision: str = "{old_rev}"',
        f'revision: str = "{new_rev}"',
        content
    )
    
    # Replace down_revision if specified
    if old_down and new_down:
        content = re.sub(
            f'down_revision: str \\| None = "{old_down}"',
            f'down_revision: str | None = "{new_down}"',
            content
        )
    
    file_path.write_text(content)
    print(f"✅ Fixed {file_path.name}: {old_rev} → {new_rev}")

print("\n🎉 All migrations fixed!")
