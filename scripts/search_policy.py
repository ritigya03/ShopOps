#!/usr/bin/env python3
"""Interactive demo of the search_policy retrieval path.

Type a natural-language question; this embeds it with the same model
used at ingestion time and shows the top-ranked policy passages Qdrant
returns, with scores — the same lookup search_policy will eventually do.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COLLECTION_NAME = "shopops_policy"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    client = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))

    print(f"Connected to Qdrant. Collection '{COLLECTION_NAME}' ready.")
    print("Type a question about delivery, compensation, or seller policy.")
    print("Type 'quit' to exit.\n")

    while True:
        query = input("> ").strip()
        if not query or query.lower() in ("quit", "exit"):
            break

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=models.Document(text=query, model=EMBEDDING_MODEL),
            limit=3,
        )

        if not results.points:
            print("  (no results)\n")
            continue

        for point in results.points:
            p = point.payload
            print(f"\n  [{point.score:.3f}] {p['doc_id']} v{p['version']} - \"{p['section']}\"")
            print(f"  {p['excerpt'][:220]}...")
        print()


if __name__ == "__main__":
    main()
