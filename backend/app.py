# backend/app.py
import os, io, uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv

# Load env
load_dotenv()
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_store")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required for Gemini embeddings")

# Configure Gemini
import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

# FastAPI app
app = FastAPI(title="RAG Ingest + Query (Gemini Embeddings)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Chroma (local persistent)
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

COLLECTION_NAME = "documents_gemini"  # Changed to avoid conflicts with old collection
try:
    collection = chroma_client.get_collection(COLLECTION_NAME)
except Exception:
    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        # We'll manually provide embeddings, so no need for Chroma's embedding function
    )

# ---------- Gemini Embedding Helper ----------
def get_gemini_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Get embeddings from Gemini embedding model
    """
    try:
        # Use the embedding model
        embedding_model = "models/embedding-001"
        
        # Gemini has limits on batch size and total tokens, so we'll process in smaller batches
        batch_size = 50  # Adjust based on your needs
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Get embeddings for the batch
            result = genai.embed_content(
                model=embedding_model,
                content=batch,
                task_type="retrieval_document"  # Use "retrieval_query" for query embeddings
            )
            
            batch_embeddings = result['embedding']
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini embedding error: {str(e)}")

def get_gemini_query_embedding(query: str) -> List[float]:
    """
    Get embedding for a single query using Gemini
    """
    try:
        embedding_model = "models/embedding-001"
        
        result = genai.embed_content(
            model=embedding_model,
            content=query,
            task_type="retrieval_query"  # Specific task type for queries
        )
        
        return result['embedding']
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini query embedding error: {str(e)}")

# ---------- Text Processing Helpers ----------
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
    """
    Split text into chunks with overlap
    Gemini embedding model has 2048 token limit, so we're safe with these chunk sizes
    """
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

# ---------- Pydantic Models ----------
class QueryIn(BaseModel):
    query: str
    top_k: Optional[int] = 4

# ---------- Routes ----------
@app.post("/ingest")
async def ingest(file: UploadFile = File(...), namespace: Optional[str] = Form("default")):
    """
    Upload file -> extract -> chunk -> embed with Gemini -> store in Chroma
    """
    # Validate file size (optional)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        return {"success": False, "error": "File too large. Maximum size is 50MB."}

    text = extract_text_from_file(file.filename, content)
    if not text or len(text.strip()) < 20:
        return {"success": False, "error": "No text extracted or file too small."}

    chunks = chunk_text(text)
    
    try:
        # Get embeddings from Gemini
        embeddings = get_gemini_embeddings(chunks)
    except Exception as e:
        return {"success": False, "error": f"Embedding failed: {str(e)}"}

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": file.filename, "chunk_index": i, "namespace": namespace} for i in range(len(chunks))]
    documents = chunks

    # Add to collection
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings
    )
    
    return {
        "success": True, 
        "ingested_chunks": len(chunks), 
        "file": file.filename,
        "embedding_model": "Gemini embedding-001"
    }

@app.post("/query")
async def query(q: QueryIn):
    query_text = q.query
    top_k = q.top_k or 4

    try:
        # Get query embedding from Gemini
        q_emb = get_gemini_query_embedding(query_text)
    except Exception as e:
        return {"success": False, "error": f"Query embedding failed: {str(e)}"}

    # Query chroma
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

    # Generate answer using Gemini
    try:
        # Use Gemini for final answer generation
        selected_model = "models/gemini-2.0-flash"
        model = genai.GenerativeModel(selected_model)
        
        prompt = f"""Based on the following context, please answer the question concisely and accurately.

Context:
{context}

Question: {query_text}

If the context doesn't contain relevant information, say so clearly.

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
            answer = f"(Gemini generation error) {str(e2)}"

    return {
        "query": query_text, 
        "top_k": top_k, 
        "documents": docs, 
        "answer": answer,
        "embedding_model": "Gemini embedding-001"
    }

@app.get("/collections")
def list_collections():
    cols = chroma_client.list_collections()
    return {"collections": [{"name": c.name} for c in cols]}

@app.get("/collection_info")
def collection_info():
    """Get information about the current collection"""
    count = collection.count()
    return {
        "collection_name": COLLECTION_NAME,
        "document_count": count,
        "embedding_model": "Gemini embedding-001"
    }

@app.post("/flush")
def flush_data():
    """Clear all data from the collection"""
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        global collection
        collection = chroma_client.create_collection(name=COLLECTION_NAME)
        return {"success": True, "message": "Collection flushed successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/")
async def root():
    return {"message": "RAG API with Gemini Embeddings", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)