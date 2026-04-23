"""
store_index.py — Index all documents in data/ into Pinecone.

Usage:
    python store_index.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Validate env vars early ────────────────────────────────────────────────────
required_vars = ["PINECONE_API_KEY", "PINECONE_INDEX_NAME", "GROQ_API_KEY"]
missing = [v for v in required_vars if not os.environ.get(v)]
if missing:
    print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
    print("Copy .env.example to .env and fill in your keys.")
    sys.exit(1)

from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    UnstructuredMarkdownLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone, ServerlessSpec


DATA_DIR = Path(__file__).parent / "data"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
BATCH_SIZE = 100


def load_documents(data_dir: Path):
    """Load all supported files from data/ directory."""
    docs = []
    supported = {".txt": TextLoader, ".md": UnstructuredMarkdownLoader, ".pdf": PyPDFLoader}

    files = list(data_dir.iterdir()) if data_dir.exists() else []
    if not files:
        print(f"[WARN] No files found in {data_dir}. Creating a sample document...")
        sample_path = data_dir / "namma_yatri_overview.txt"
        sample_path.write_text(
            """Namma Yatri Overview
Namma Yatri is an open-source, zero-commission ride-hailing application developed under the
Juspay Technologies umbrella and backed by the Government of Karnataka. It operates on the
Open Network for Digital Commerce (ONDC) protocol, ensuring interoperability and transparency.

Key Differentiators:
- Zero commission model: Drivers retain 100% of their fare earnings.
- Open source: The entire codebase is publicly available on GitHub.
- Government backed: Supported by BBMP and other Karnataka government bodies.
- ONDC protocol: Built on India's open commerce network for maximum interoperability.

Cities of Operation (2024-2025):
- Bangalore (largest market)
- Chennai
- Hyderabad
- Mysore
- Kochi

Business Model:
Namma Yatri monetizes through a subscription model where drivers pay a fixed weekly/monthly
fee (around ₹25-50/week) rather than per-ride commissions. This is a fundamental disruption
to the Ola/Uber model where 20-30% commission is charged per ride.

Driver Benefits:
- Keep 100% of ride earnings
- No surge commission deductions
- Transparent pricing
- Community-driven support

Rider Benefits:
- Transparent pricing without hidden surge markups
- Direct connection with drivers
- Lower fares due to no commission overhead
- Safety features: live tracking, SOS button, trip sharing

Technology Stack:
- Mobile: React Native (Android & iOS)
- Backend: Haskell (Beckn protocol), Node.js
- Infrastructure: AWS
- Protocol: ONDC / Beckn

Funding & Growth:
Namma Yatri reached 50 lakh (5 million) rides milestone in its first year. It has received
backing from the Karnataka government and various Indian startup ecosystem supporters.

Competitive Landscape:
- Ola: 20-25% commission, corporate-backed, pan-India
- Uber: 25-30% commission, global player, premium positioning
- Rapido: Bike taxi focus, 15-20% commission
- InDrive: Negotiable pricing model, expanding in India
- Namma Yatri: Zero commission, open source, ONDC-based

Product Roadmap Themes (2025-2026):
1. Driver retention and earnings optimization
2. Scheduled rides and advance booking
3. Safety feature enhancements
4. City expansion (Tier 2 cities)
5. Bike taxi vertical
6. Corporate ride accounts
7. Multilingual support expansion
8. Accessibility improvements for differently-abled users
""",
            encoding="utf-8",
        )
        print(f"[OK] Sample document created at {sample_path}")
        files = list(data_dir.iterdir())

    print(f"\n[STEP 1] Loading documents from {data_dir}/ ...")
    for f in files:
        suffix = f.suffix.lower()
        loader_cls = supported.get(suffix)
        if loader_cls is None:
            print(f"  [SKIP] Unsupported file type: {f.name}")
            continue
        try:
            loader = loader_cls(str(f))
            loaded = loader.load()
            docs.extend(loaded)
            print(f"  [OK] Loaded {len(loaded)} page(s) from {f.name}")
        except Exception as e:
            print(f"  [ERROR] Failed to load {f.name}: {e}")

    print(f"[DONE] Total documents loaded: {len(docs)}")
    return docs


def split_documents(docs):
    """Split documents into chunks."""
    print(f"\n[STEP 2] Splitting into chunks (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}) ...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    print(f"[DONE] Total chunks created: {len(chunks)}")
    return chunks


def get_or_create_index(pc: Pinecone, index_name: str, dimension: int):
    """Get existing Pinecone index or create a new one."""
    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        print(f"\n[STEP 3] Creating Pinecone index '{index_name}' (dim={dimension}) ...")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print(f"[DONE] Index '{index_name}' created.")
    else:
        print(f"\n[STEP 3] Using existing Pinecone index '{index_name}'.")
    return pc.Index(index_name)


def embed_and_upsert(index, chunks, embeddings_model):
    """Embed chunks and upsert to Pinecone in batches."""
    print(f"\n[STEP 4] Embedding {len(chunks)} chunks with {EMBEDDING_MODEL} ...")
    total = len(chunks)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]
        texts = [c.page_content for c in batch]
        vectors = embeddings_model.embed_documents(texts)

        records = []
        for i, (chunk, vector) in enumerate(zip(batch, vectors)):
            global_idx = batch_start + i
            records.append(
                {
                    "id": f"chunk-{global_idx}",
                    "values": vector,
                    "metadata": {
                        "text": chunk.page_content,
                        "source": chunk.metadata.get("source", "unknown"),
                        "chunk_index": global_idx,
                        "total_chunks": total,
                    },
                }
            )

        index.upsert(vectors=records)
        pct = min(batch_start + BATCH_SIZE, total)
        print(f"  [PROGRESS] Upserted {pct}/{total} chunks ...")

    print(f"[DONE] All {total} chunks upserted to Pinecone.")


def main():
    print("=" * 60)
    print("  ARIA — Namma Yatri Knowledge Base Indexer")
    print("=" * 60)

    docs = load_documents(DATA_DIR)
    if not docs:
        print("[ERROR] No documents to index. Exiting.")
        sys.exit(1)

    chunks = split_documents(docs)

    print(f"\n[STEP 3] Loading embedding model: {EMBEDDING_MODEL} ...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    sample_vec = embeddings.embed_query("test")
    dim = len(sample_vec)
    print(f"[DONE] Embedding model loaded. Vector dimension: {dim}")

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.environ.get("PINECONE_INDEX_NAME", "namma-aria")
    index = get_or_create_index(pc, index_name, dim)

    embed_and_upsert(index, chunks, embeddings)

    print("\n" + "=" * 60)
    print("  Indexing complete! ARIA knowledge base is ready.")
    print(f"  Index: {index_name} | Chunks: {len(chunks)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
