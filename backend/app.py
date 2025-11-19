# backend/app.py (Pinecone NEW Version)
import os, io, uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from PyPDF2 import PdfReader
from docx import Document
from dotenv import load_dotenv
from datetime import datetime, timedelta
import re
import nltk


# Download NLTK data on startup
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("Downloading NLTK punkt data...")
    nltk.download('punkt', quiet=True)
    print("NLTK punkt data downloaded successfully!")

# Load env
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rag-documents")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

# Create upload directory
os.makedirs(UPLOAD_DIR, exist_ok=True)

# FastAPI app
app = FastAPI(title="RAG Ingest + Query (Pinecone + Auth)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rag-app-dusky.vercel.app",
        "https://your-pythonanywhere-username.pythonanywhere.com",
        "http://localhost:3000",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#  NEW PINEcone INITIALIZATION
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    print(" Pinecone client initialized successfully!")
    
    # Check if index exists, create if not
    existing_indexes = pc.list_indexes().names()
    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f" Creating new index: {PINECONE_INDEX_NAME}")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=384,  # Match sentence-transformers model
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        # Wait for index to be ready
        import time
        time.sleep(1)
    
    # Connect to index
    index = pc.Index(PINECONE_INDEX_NAME)
    print(" Pinecone index connected successfully!")
    
except Exception as e:
    print(f" Pinecone initialization failed: {e}")
    pc = None
    index = None

#  Initialize Embedding Model
try:
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print(" Embedding model loaded successfully!")
except Exception as e:
    print(f" Embedding model loading failed: {e}")
    embedding_model = None

# JWT implementation (same as before)
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

# Text processing functions (same as before)
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

def smart_sentence_chunk(text: str, sentences_per_chunk: int = 5, overlap_sentences: int = 2) -> List[str]:
    try:
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
        
        sentences = nltk.tokenize.sent_tokenize(text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 1:
            return chunk_text(text)
        
        chunks = []
        i = 0
        
        while i < len(sentences):
            end_idx = min(i + sentences_per_chunk, len(sentences))
            chunk_sentences = sentences[i:end_idx]
            chunk = " ".join(chunk_sentences)
            chunks.append(chunk)
            i += (sentences_per_chunk - overlap_sentences)
            if i >= len(sentences):
                break
        
        return chunks
        
    except Exception as e:
        print(f"Sentence chunking failed, using fallback: {e}")
        return chunk_text(text)

def smart_chunk_text(text: str, method: str = "sentence", **kwargs) -> List[str]:
    if method == "sentence":
        return smart_sentence_chunk(text, **kwargs)
    else:
        return chunk_text(text, **kwargs)

#  PINEcone EMBEDDING FUNCTIONS
def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using local model for Pinecone"""
    if not embedding_model:
        raise HTTPException(status_code=500, detail="Embedding model not available")
    
    try:
        embeddings = embedding_model.encode(texts)
        return embeddings.tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")

def get_query_embedding(query: str) -> List[float]:
    """Generate embedding for a single query"""
    if not embedding_model:
        raise HTTPException(status_code=500, detail="Embedding model not available")
    
    try:
        embedding = embedding_model.encode([query])
        return embedding[0].tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query embedding failed: {str(e)}")

# Pydantic models
class QueryIn(BaseModel):
    query: str
    top_k: Optional[int] = 50
    page: Optional[int] = 1
    page_size: Optional[int] = 10

class PaginationInfo(BaseModel):
    current_page: int
    page_size: int
    total_results: int
    total_pages: int
    has_next: bool
    has_previous: bool

#  PINEcone INGEST ENDPOINT (UPDATED)
@app.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user)
):
    if not index:
        return {"success": False, "error": "Pinecone not available"}
    
    # Save file
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    if len(content) > 50 * 1024 * 1024:
        return {"success": False, "error": "File too large. Maximum size is 50MB."}

    text = extract_text_from_file(file.filename, content)
    if not text or len(text.strip()) < 20:
        return {"success": False, "error": "No text extracted or file too small."}

    # Chunk text
    chunks = smart_chunk_text(
        text, 
        method="sentence",
        sentences_per_chunk=5,
        overlap_sentences=2
    )
    
    # Generate embeddings
    try:
        embeddings = get_embeddings(chunks)
    except Exception as e:
        return {"success": False, "error": f"Embedding failed: {str(e)}"}
    
    #  NEW PINEcone DATA FORMAT
    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        vector_id = f"{current_user.user_id}_{file_id}_{i}"
        
        metadata = {
            "text": chunk,
            "source": file.filename,
            "chunk_index": i,
            "user_id": current_user.user_id,
            "username": current_user.username,
            "document_id": file_id,
            "file_path": file_path,
            "upload_time": datetime.utcnow().isoformat(),
            "chunking_method": "sentence_based",
        }
        
        vectors.append({
            "id": vector_id,
            "values": embedding,
            "metadata": metadata
        })
    
    #  NEW PINEcone UPSERT
    try:
        # Upsert in batches of 100
        for i in range(0, len(vectors), 100):
            batch = vectors[i:i + 100]
            index.upsert(vectors=batch)
        
        return {
            "success": True, 
            "ingested_chunks": len(chunks), 
            "file": file.filename,
            "user_id": current_user.user_id,
            "document_id": file_id
        }
        
    except Exception as e:
        return {"success": False, "error": f"Pinecone upload failed: {str(e)}"}

#  PINEcone QUERY ENDPOINT (UPDATED)
@app.post("/query")
async def query(
    q: QueryIn,
    current_user: TokenData = Depends(get_current_user)
):
    if not index:
        return {"success": False, "error": "Pinecone not available"}
    
    # Generate query embedding
    try:
        query_embedding = get_query_embedding(q.query)
    except Exception as e:
        return {"success": False, "error": f"Query embedding failed: {str(e)}"}
    
    # NEW PINEcone QUERY
    try:
        results = index.query(
            vector=query_embedding,
            top_k=min(q.top_k or 50, 100),
            filter={"user_id": {"$eq": current_user.user_id}},
            include_metadata=True,
            include_values=False
        )
        
        total_results = len(results.matches)
        
        # Pagination
        page_size = q.page_size or 10
        current_page = q.page or 1
        start_idx = (current_page - 1) * page_size
        end_idx = start_idx + page_size
        
        total_pages = (total_results + page_size - 1) // page_size if total_results > 0 else 1
        
        # Get paginated results
        paginated_matches = results.matches[start_idx:end_idx]
        
        docs = []
        for match in paginated_matches:
            metadata = match.metadata
            docs.append({
                "text": metadata.get("text", ""),
                "metadata": metadata,
                "distance": 1 - match.score,  # Convert similarity to distance
                "relevance_score": round(match.score * 100, 1),
                "chunk_id": match.id,
                "source_link": f"/api/documents/{metadata.get('document_id', '')}",
                "upload_time": metadata.get('upload_time', ''),
                "chunk_number": metadata.get('chunk_index', 0) + 1
            })
        
        context = "\n\n---\n\n".join([d["text"] for d in docs])
        
        if docs:
            answer = f"Based on your documents, here's what I found (showing {len(docs)} of {total_results} relevant sources):\n\n{context}"
        else:
            answer = "I couldn't find any relevant information in your uploaded documents to answer this question."
        
        return {
            "query": q.query, 
            "documents": docs, 
            "answer": answer,
            "user_id": current_user.user_id,
            "pagination": {
                "current_page": current_page,
                "page_size": page_size,
                "total_results": total_results,
                "total_pages": total_pages,
                "has_next": current_page < total_pages,
                "has_previous": current_page > 1
            }
        }
        
    except Exception as e:
        return {"success": False, "error": f"Pinecone query failed: {str(e)}"}

#  PINEcone DOCUMENT MANAGEMENT (UPDATED)
@app.get("/user/documents")
async def get_user_documents(current_user: TokenData = Depends(get_current_user)):
    """Get all documents for the current user from Pinecone"""
    if not index:
        return {"success": False, "error": "Pinecone not available"}
    
    try:
        #  NEW PINEcone QUERY FOR ALL DOCUMENTS
        # We need to query with a dummy vector to get all user documents
        dummy_vector = [0] * 384  # Match embedding dimension
        
        results = index.query(
            vector=dummy_vector,
            top_k=10000,
            filter={"user_id": {"$eq": current_user.user_id}},
            include_metadata=True
        )
        
        documents_by_id = {}
        for match in results.matches:
            metadata = match.metadata
            document_id = metadata.get("document_id")
            filename = metadata.get("source", "Unknown")
            
            if document_id not in documents_by_id:
                documents_by_id[document_id] = {
                    "filename": filename,
                    "chunks": 0,
                    "uploaded_by": metadata.get("username", ""),
                    "upload_time": metadata.get("upload_time", ""),
                    "document_id": document_id
                }
            documents_by_id[document_id]["chunks"] += 1
        
        documents_list = list(documents_by_id.values())
        
        return {
            "user_id": current_user.user_id,
            "username": current_user.username,
            "total_documents": len(documents_list),
            "total_chunks": len(results.matches),
            "documents": documents_list
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/user/flush")
async def flush_user_data(current_user: TokenData = Depends(get_current_user)):
    """Clear all data for the current user from Pinecone"""
    if not index:
        return {"success": False, "error": "Pinecone not available"}
    
    try:
        #  NEW PINEcone DELETE
        index.delete(filter={"user_id": {"$eq": current_user.user_id}})
        
        return {
            "success": True, 
            "message": f"All documents for user {current_user.username} flushed successfully",
            "user_id": current_user.user_id
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Test endpoints
@app.get("/test")
async def test():
    pinecone_status = "connected" if index else "disconnected"
    return {
        "message": f"Server is working with Pinecone ({pinecone_status})!", 
        "status": "OK"
    }

@app.get("/")
async def root():
    pinecone_status = "connected" if index else "disconnected"
    return {
        "message": f"RAG API with Pinecone ({pinecone_status}) - Server is running!", 
        "status": "running"
    }

# Document provenance endpoints (simplified for now)
@app.get("/api/documents/{document_id}")
async def get_document_info(document_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        # Query for documents with this document_id
        dummy_vector = [0] * 384
        results = index.query(
            vector=dummy_vector,
            top_k=1,
            filter={
                "user_id": {"$eq": current_user.user_id},
                "document_id": {"$eq": document_id}
            },
            include_metadata=True
        )
        
        if not results.matches:
            raise HTTPException(status_code=404, detail="Document not found")
        
        metadata = results.matches[0].metadata
        return {
            "document_id": document_id,
            "filename": metadata.get("source", "Unknown"),
            "uploaded_by": metadata.get("username", "Unknown"),
            "upload_time": metadata.get("upload_time", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving document: {str(e)}")

@app.get("/api/documents/{document_id}/download")
async def download_document(document_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        # Query to get file path
        dummy_vector = [0] * 384
        results = index.query(
            vector=dummy_vector,
            top_k=1,
            filter={
                "user_id": {"$eq": current_user.user_id},
                "document_id": {"$eq": document_id}
            },
            include_metadata=True
        )
        
        if not results.matches:
            raise HTTPException(status_code=404, detail="Document not found")
        
        metadata = results.matches[0].metadata
        file_path = metadata.get("file_path")
        
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Original file not found")
        
        filename = metadata.get("source", "document")
        
        from fastapi.responses import FileResponse
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading document: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5005)