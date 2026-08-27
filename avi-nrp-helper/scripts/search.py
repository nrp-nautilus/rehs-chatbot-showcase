import os
import json
import chromadb
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path

load_dotenv()
client = OpenAI(api_key=os.environ["NRP_LLM_TOKEN"],
                base_url=os.environ.get("NRP_LLM_BASE_URL", "https://ellm.nrp-nautilus.io/v1"))

chunks = []

for file in Path("data/chunks").glob("*.json"):
    with open(file, encoding="utf-8") as f:
        chunks.append(json.load(f))

def embed(text: str) -> list[float]:
    return client.embeddings.create(model="qwen3-embedding", input=[text]).data[0].embedding

coll = chromadb.PersistentClient(path="./chroma_db").get_or_create_collection("nrp_docs")

def search(query: str, k: int = 5) -> list[dict]:
    res = coll.query(query_embeddings=[embed(query)], n_results=k)
    return [
        {"text": d, "source_url": m["source_url"], "title": m["title"], "score": s}
        for d, m, s in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
 