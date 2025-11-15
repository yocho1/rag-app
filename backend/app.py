# backend/app.py
import os, io, uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import chromadb
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv

# Optional Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

# Load env
load_dotenv()
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_store")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY and GEMINI_AVAILABLE:
    genai.configure(api_key=GEMINI_API_KEY)

# FastAPI app
app = FastAPI(title="RAG Ingest + Query")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Chroma (local persistent) - FIXED VERSION
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

COLLECTION_NAME = "documents"
try:
    collection = chroma_client.get_collection(COLLECTION_NAME)
except Exception:
    collection = chroma_client.create_collection(name=COLLECTION_NAME)

# Embedding model (local)
embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

# ---------- helpers ----------
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    texts = []
    for p in reader.pages:
        txt = p.extract_text()
        if txt:
            texts.append(txt)
    return "\n".join(texts)

def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join([p.text for p in doc.paragraphs])

def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    fname = filename.lower()
    if fname.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if fname.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    # fallback plain text
    try:
        return file_bytes.decode("utf-8")
    except Exception:
        return file_bytes.decode("latin-1", errors="ignore")

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    text = text.replace("\r\n", "\n")
    chunks = []
    start = 0
    L = len(text)
    while start < L:
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0
    return chunks

def embed_texts(texts: List[str]) -> List[List[float]]:
    embs = embedder.encode(texts, show_progress_bar=False)
    # sentence-transformers returns numpy array; convert to list
    return [e.tolist() if hasattr(e, "tolist") else list(e) for e in embs]

# ---------- Pydantic ----------
class QueryIn(BaseModel):
    query: str
    top_k: Optional[int] = 4

# ---------- Routes ----------
@app.post("/ingest")
async def ingest(file: UploadFile = File(...), namespace: Optional[str] = Form("default")):
    """
    Upload file -> extract -> chunk -> embed -> store in Chroma collection.
    namespace currently unused but reserved for per-user separation.
    """
    content = await file.read()
    text = extract_text_from_file(file.filename, content)
    if not text or len(text.strip()) < 20:
        return {"success": False, "error": "No text extracted or file too small."}

    chunks = chunk_text(text)
    embeddings = embed_texts(chunks)

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": file.filename, "chunk_index": i} for i in range(len(chunks))]
    documents = chunks

    # Add to collection
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings
    )
    # REMOVED: chroma_client.persist()
    return {"success": True, "ingested_chunks": len(chunks), "file": file.filename}

# In the query endpoint, replace the Gemini section:
@app.post("/query")
async def query(q: QueryIn):
    query_text = q.query
    top_k = q.top_k or 4

    # embed query
    q_emb = embed_texts([query_text])[0]

    # query chroma
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=['documents', 'metadatas', 'distances']
    )

    docs = []
    for idx, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][idx] if results.get("metadatas") else {}
        dist = results["distances"][0][idx] if results.get("distances") else None
        docs.append({"text": doc, "metadata": meta, "distance": dist})

    context = "\n\n---\n\n".join([d["text"] for d in docs])

    # If Gemini available -> call to produce final answer
    answer = None
    if GEMINI_API_KEY and GEMINI_AVAILABLE:
        try:
            # Use one of the available models - gemini-2.0-flash is fast and reliable
            selected_model = "models/gemini-2.0-flash"
            model = genai.GenerativeModel(selected_model)
            
            prompt = f"""Based on the following context, please answer the question concisely and accurately.

Context:
{context}

Question: {query_text}

Answer:"""
            
            resp = model.generate_content(prompt)
            answer = resp.text.strip()
                
        except Exception as e:
            # Fallback to a different model if the first one fails
            try:
                selected_model = "models/gemini-2.0-flash-lite"
                model = genai.GenerativeModel(selected_model)
                resp = model.generate_content(prompt)
                answer = resp.text.strip()
            except Exception as e2:
                answer = f"(Gemini error) {str(e2)}"
    else:
        answer = "No Gemini key configured. Returning retrieved context."

    return {"query": query_text, "top_k": top_k, "documents": docs, "answer": answer}

@app.get("/collections")
def list_collections():
    cols = chroma_client.list_collections()
    return {"collections": [{"name": c.name} for c in cols]}

@app.post("/flush")
def flush_data():
    # CAUTION: removes the collection
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        global collection
        collection = chroma_client.create_collection(name=COLLECTION_NAME)
        # REMOVED: chroma_client.persist()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}