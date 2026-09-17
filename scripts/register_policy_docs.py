#!/usr/bin/env python3
"""Register data/policy/*.md metadata into shopops_ops.policy_documents.

The markdown files are the source of truth for policy content; this just
syncs their doc_id/version/status/checksum into the control-plane table so
the agent layer (and eventually RAG ingestion) can look up which policy
versions are active. Safe to re-run: upserts on (doc_id, version).
"""
import hashlib
import os
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_DIR = PROJECT_ROOT / "data" / "policy"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_doc(path: Path):
    text_content = path.read_text()
    match = FRONTMATTER_RE.match(text_content)
    if not match:
        sys.exit(f"{path.name}: missing YAML frontmatter block")
    meta = yaml.safe_load(match.group(1))
    checksum = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
    return meta, checksum


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL not set. Copy .env.example to .env and fill it in.")
    engine = create_engine(database_url)

    files = sorted(POLICY_DIR.glob("*.md"))
    if not files:
        sys.exit(f"No policy documents found in {POLICY_DIR}")

    with engine.begin() as conn:
        for path in files:
            meta, checksum = parse_doc(path)
            conn.execute(
                text("""
                    INSERT INTO shopops_ops.policy_documents
                        (doc_id, version, title, domain, effective_from, status, checksum, source_uri)
                    VALUES
                        (:doc_id, :version, :title, :domain, :effective_from, :status, :checksum, :source_uri)
                    ON CONFLICT (doc_id, version) DO UPDATE SET
                        title = EXCLUDED.title,
                        domain = EXCLUDED.domain,
                        effective_from = EXCLUDED.effective_from,
                        status = EXCLUDED.status,
                        checksum = EXCLUDED.checksum,
                        source_uri = EXCLUDED.source_uri
                """),
                {
                    "doc_id": meta["doc_id"],
                    "version": str(meta["version"]),
                    "title": meta["title"],
                    "domain": meta["domain"],
                    "effective_from": meta["effective_from"],
                    "status": meta["status"],
                    "checksum": checksum,
                    "source_uri": f"data/policy/{path.name}",
                },
            )
            print(f"  registered {meta['doc_id']} v{meta['version']} ({path.name})")

    print(f"Done. {len(files)} policy document(s) registered.")


if __name__ == "__main__":
    main()
