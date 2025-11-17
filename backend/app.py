# backend/app.py
import os, io, uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load env
load_dotenv()
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_store")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")

# FastAPI app
app = FastAPI(title="RAG Ingest + Query (Local Embeddings + Auth)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Chroma with LOCAL embeddings
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

# Use sentence-transformers for local embeddings
embedding_function = SentenceTransformerEmbeddingFunction()

COLLECTION_NAME = "documents_local_auth"

try:
    collection = chroma_client.get_collection(
        COLLECTION_NAME, 
        embedding_function=embedding_function
    )
except Exception:
    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function
    )

# JWT implementation
security = HTTPBearer()

class TokenData(BaseModel):
    user_id: str
    username: str

def create_jwt_token(user_id: str, username: str) -> str:
    """Create JWT token"""
    try:
        import jwt
        expiration = datetime.utcnow() + timedelta(hours=24)
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": expiration
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    except ImportError:
        # Fallback without JWT
        return f"simple-token-{user_id}-{username}"

def verify_jwt_token(token: str) -> TokenData:
    """Verify JWT token"""
    try:
        import jwt
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        return TokenData(
            user_id=payload.get("user_id", "unknown"),
            username=payload.get("username", "unknown")
        )
    except ImportError:
        # Fallback for simple tokens
        if token.startswith("simple-token-"):
            parts = token.split("-")
            if len(parts) >= 4:
                return TokenData(user_id=parts[2], username=parts[3])
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    return verify_jwt_token(credentials.credentials)

# Authentication routes
class LoginRequest(BaseModel):
    username: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    username: str

@app.post("/auth/login", response_model=LoginResponse)
async def login(login_data: LoginRequest):
    user_id = str(uuid.uuid4())
    token = create_jwt_token(user_id, login_data.username)
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_id,
        username=login_data.username
    )

@app.get("/auth/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    return current_user

# Test route
@app.get("/test")
async def test():
    return {"message": "Server is working!", "status": "OK"}

@app.get("/")
async def root():
    return {"message": "RAG API with Auth - Server is running!", "status": "running"}

# Text processing functions
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join([p.text for p in doc.paragraphs])

def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    fname = filename.lower()
    if fname.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if fname.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
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
    return chunks

# Pydantic models
class QueryIn(BaseModel):
    query: str
    top_k: Optional[int] = 4

# Protected routes - UPDATED for local embeddings
@app.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user)
):
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return {"success": False, "error": "File too large. Maximum size is 50MB."}

    text = extract_text_from_file(file.filename, content)
    if not text or len(text.strip()) < 20:
        return {"success": False, "error": "No text extracted or file too small."}

    chunks = chunk_text(text)
    
    # No need for manual embeddings - ChromaDB handles it automatically
    user_namespace = f"user_{current_user.user_id}"
    
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{
        "source": file.filename, 
        "chunk_index": i, 
        "namespace": user_namespace,
        "user_id": current_user.user_id,
        "username": current_user.username
    } for i in range(len(chunks))]

    # ChromaDB will automatically generate embeddings using the SentenceTransformer
    collection.add(
        ids=ids,
        documents=chunks,
        metadatas=metadatas
        # No embeddings parameter needed - ChromaDB generates them automatically
    )
    
    return {
        "success": True, 
        "ingested_chunks": len(chunks), 
        "file": file.filename,
        "user_id": current_user.user_id
    }

@app.post("/query")
async def query(
    q: QueryIn,
    current_user: TokenData = Depends(get_current_user)
):
    # No need for manual query embedding - ChromaDB handles it automatically
    
    user_filter = {"user_id": current_user.user_id}
    
    # ChromaDB will automatically embed the query using the same model
    results = collection.query(
        query_texts=[q.query],  # Use query_texts instead of query_embeddings
        n_results=q.top_k or 4,
        where=user_filter,
        include=['documents', 'metadatas', 'distances']
    )

    docs = []
    for idx, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][idx] if results.get("metadatas") else {}
        dist = results["distances"][0][idx] if results.get("distances") else None
        docs.append({"text": doc, "metadata": meta, "distance": dist})

    context = "\n\n---\n\n".join([d["text"] for d in docs])

    # For the answer generation, we can still use Gemini if you want, or use a local model
    # Let's use a simple template-based answer for now to avoid API limits
    if docs:
        answer = f"Based on your documents, here's what I found:\n\n{context}\n\nThis information is retrieved from your uploaded documents."
    else:
        answer = "I couldn't find any relevant information in your uploaded documents to answer this question. Please make sure you've uploaded relevant documents first."
    
    return {
        "query": q.query, 
        "top_k": q.top_k or 4,
        "documents": docs, 
        "answer": answer,
        "user_id": current_user.user_id
    }

@app.get("/user/documents")
async def get_user_documents(current_user: TokenData = Depends(get_current_user)):
    """Get all documents for the current user"""
    try:
        user_filter = {"user_id": current_user.user_id}
        results = collection.get(where=user_filter)
        
        documents_by_source = {}
        for i, metadata in enumerate(results["metadatas"]):
            source = metadata.get("source", "Unknown")
            if source not in documents_by_source:
                documents_by_source[source] = {
                    "chunks": 0,
                    "namespace": metadata.get("namespace", ""),
                    "uploaded_by": metadata.get("username", "")
                }
            documents_by_source[source]["chunks"] += 1
        
        return {
            "user_id": current_user.user_id,
            "username": current_user.username,
            "total_documents": len(documents_by_source),
            "total_chunks": len(results["ids"]),
            "documents": documents_by_source
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/user/flush")
async def flush_user_data(current_user: TokenData = Depends(get_current_user)):
    """Clear all data for the current user"""
    try:
        user_filter = {"user_id": current_user.user_id}
        collection.delete(where=user_filter)
        return {
            "success": True, 
            "message": f"All documents for user {current_user.username} flushed successfully",
            "user_id": current_user.user_id
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Add this right after your FastAPI app initialization
@app.get("/debug/routes")
async def debug_routes():
    routes = []
    for route in app.routes:
        route_info = {
            "path": getattr(route, "path", None),
            "methods": getattr(route, "methods", None),
            "name": getattr(route, "name", None)
        }
        routes.append(route_info)
    return {"routes": routes}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)