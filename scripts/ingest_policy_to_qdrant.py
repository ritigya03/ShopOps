#!/usr/bin/env python3
"""Chunk and embed data/policy/*.md into Qdrant for search_policy.

Per the Technical Design Document §7 (RAG and Knowledge Architecture):
ingest -> parse -> section-aware chunks -> embed -> Qdrant collection.
Each "## " heading in a policy file becomes one chunk, tagged with the
metadata search_policy needs to cite a source (doc_id, version, section).

Uses Qdrant's built-in FastEmbed integration (all-MiniLM-L6-v2, 384-dim)
so no external embedding API key is required. Safe to re-run: recreates
the collection each time.
"""
import os
import re
import sys
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_DIR = PROJECT_ROOT / "data" / "policy"
COLLECTION_NAME = "shopops_policy"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def parse_sections(path: Path):
    raw = path.read_text()
    match = FRONTMATTER_RE.match(raw)
    if not match:
        sys.exit(f"{path.name}: missing YAML frontmatter block")
    meta = yaml.safe_load(match.group(1))
    body = match.group(2)

    headings = list(SECTION_RE.finditer(body))
    if not headings:
        sys.exit(f"{path.name}: no '## ' section headings found to chunk on")

    sections = []
    for i, h in enumerate(headings):
        start = h.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        sections.append((h.group(1).strip(), body[start:end].strip()))
    return meta, sections


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=qdrant_url)

    files = sorted(POLICY_DIR.glob("*.md"))
    if not files:
        sys.exit(f"No policy documents found in {POLICY_DIR}")

    documents, metadatas, ids = [], [], []
    for path in files:
        meta, sections = parse_sections(path)
        for chunk_index, (section_title, section_text) in enumerate(sections):
            chunk_id = f"{meta['doc_id']}-v{meta['version']}-{chunk_index}"
            documents.append(f"{meta['title']} - {section_title}\n\n{section_text}")
            metadatas.append({
                "chunk_id": chunk_id,
                "doc_id": meta["doc_id"],
                "document_title": meta["title"],
                "version": str(meta["version"]),
                "domain": meta["domain"],
                "effective_from": str(meta["effective_from"]),
                "status": meta["status"],
                "source_uri": f"data/policy/{path.name}",
                "section": section_title,
                "chunk_index": chunk_index,
                "excerpt": section_text[:500],
                "embedding_model": EMBEDDING_MODEL,
            })
            # Qdrant point IDs must be an unsigned int or UUID; derive a
            # stable UUID from our human-readable chunk_id so re-running
            # this script upserts the same points instead of duplicating.
            ids.append(str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)))
        print(f"  parsed {path.name}: {len(sections)} section(s)")

    vector_size, distance = client.get_embedding_size(EMBEDDING_MODEL), models.Distance.COSINE
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=vector_size, distance=distance),
    )

    points = [
        models.PointStruct(
            id=point_id,
            vector=models.Document(text=doc_text, model=EMBEDDING_MODEL),
            payload=payload,
        )
        for point_id, doc_text, payload in zip(ids, documents, metadatas)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)

    print(f"\nIndexed {len(documents)} chunks from {len(files)} document(s) "
          f"into Qdrant collection '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
