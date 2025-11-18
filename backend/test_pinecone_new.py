# test_pinecone_windows.py - Windows compatible version
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rag-documents")

print("Testing NEW Pinecone connection...")
print(f"API Key: {PINECONE_API_KEY[:10]}..." if PINECONE_API_KEY else "No API key found")

try:
    from pinecone import Pinecone, ServerlessSpec
    
    # NEW Pinecone initialization
    pc = Pinecone(api_key=PINECONE_API_KEY)
    print("SUCCESS: Pinecone client created successfully!")
    
    # List indexes
    indexes = pc.list_indexes().names()
    print(f"SUCCESS: Available indexes: {indexes}")
    
    # Check if our index exists
    if PINECONE_INDEX_NAME in indexes:
        print(f"SUCCESS: Index '{PINECONE_INDEX_NAME}' exists!")
        
        # Connect to index
        index = pc.Index(PINECONE_INDEX_NAME)
        print("SUCCESS: Successfully connected to index!")
        
        # Get index stats
        stats = index.describe_index_stats()
        print(f"SUCCESS: Index stats: {stats}")
        
        # Test a simple operation
        try:
            # Try to upsert a test vector
            test_vectors = [{
                "id": "test_vector_1",
                "values": [0.1] * 384,  # 384 dimensions for our model
                "metadata": {"test": True}
            }]
            index.upsert(vectors=test_vectors)
            print("SUCCESS: Test vector upserted successfully!")
            
            # Clean up test vector
            index.delete(ids=["test_vector_1"])
            print("SUCCESS: Test vector cleaned up!")
            
        except Exception as test_error:
            print(f"WARNING: Test operations failed (but connection works): {test_error}")
            
    else:
        print(f"INFO: Index '{PINECONE_INDEX_NAME}' doesn't exist yet")
        print("It will be created automatically when you run the app")
        
        # Optionally create the index
        create_index = input("Do you want to create the index now? (y/n): ").lower().strip()
        if create_index == 'y':
            print("Creating index...")
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=384,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            print("SUCCESS: Index created! Waiting for it to be ready...")
            import time
            time.sleep(30)  # Wait for index to initialize
            print("Index should be ready now!")
        
except ImportError as e:
    print(f"ERROR: Failed to import pinecone: {e}")
    print("Make sure you installed: pip install pinecone")
except Exception as e:
    print(f"ERROR: Pinecone error: {e}")

print("\n" + "="*50)
print("Test completed!")