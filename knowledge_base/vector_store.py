"""
Vector store using ChromaDB for persistent semantic search.
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from pathlib import Path
from typing import List, Dict, Any, Optional
from knowledge_base.embeddings import EmbeddingGenerator
from config.settings import settings
from utils.logger import logger
import uuid


class VectorStore:
    """Vector database for storing and querying embeddings."""
    
    def __init__(self, persist_directory: Path = None):
        """
        Initialize vector store.
        
        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.persist_dir = persist_directory or settings.get_chroma_path()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Initialize embedding generator
        self.embedding_generator = EmbeddingGenerator()
        
        # Collection references
        self.collections: Dict[str, chromadb.Collection] = {}
        
        logger.info(f"Initialized vector store at: {self.persist_dir}")
    
    def get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """Get or create a collection."""
        if collection_name not in self.collections:
            self.collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Loaded collection: {collection_name}")
        
        return self.collections[collection_name]
    
    def add_documents(
        self,
        collection_name: str,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ):
        """
        Add documents to a collection.
        
        Args:
            collection_name: Name of the collection
            texts: List of text content
            metadatas: List of metadata dicts
            ids: Optional list of IDs (auto-generated if not provided)
        """
        collection = self.get_or_create_collection(collection_name)
        
        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        
        # Generate embeddings
        logger.info(f"Adding {len(texts)} documents to {collection_name}...")
        embeddings = self.embedding_generator.generate_embeddings(texts)
        
        # Add to collection in batches
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch_end = min(i + batch_size, len(texts))
            
            collection.add(
                documents=texts[i:batch_end],
                embeddings=embeddings[i:batch_end],
                metadatas=metadatas[i:batch_end],
                ids=ids[i:batch_end]
            )
            
            logger.info(f"Added batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")
        
        logger.info(f"✓ Added {len(texts)} documents to {collection_name}")
    
    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = None,
        where: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Query a collection for similar documents.
        
        Args:
            collection_name: Name of the collection to query
            query_text: Query text
            n_results: Number of results to return (defaults to settings.top_k)
            where: Optional metadata filter
            
        Returns:
            Query results with documents, metadatas, and distances
        """
        collection = self.get_or_create_collection(collection_name)
        n_results = n_results or settings.top_k
        
        # Generate query embedding
        query_embedding = self.embedding_generator.generate_single_embedding(query_text)
        
        # Query collection
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where
        )
        
        return {
            'documents': results['documents'][0] if results['documents'] else [],
            'metadatas': results['metadatas'][0] if results['metadatas'] else [],
            'distances': results['distances'][0] if results['distances'] else [],
            'ids': results['ids'][0] if results['ids'] else []
        }
    
    def delete_collection(self, collection_name: str):
        """Delete a collection."""
        try:
            self.client.delete_collection(collection_name)
            if collection_name in self.collections:
                del self.collections[collection_name]
            logger.info(f"Deleted collection: {collection_name}")
        except Exception as e:
            logger.warning(f"Error deleting collection {collection_name}: {e}")
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        collections = self.client.list_collections()
        return [c.name for c in collections]
    
    def get_collection_count(self, collection_name: str) -> int:
        """Get document count in a collection."""
        collection = self.get_or_create_collection(collection_name)
        return collection.count()
    
    def reset(self):
        """Reset the entire database (dangerous!)."""
        logger.warning("Resetting vector store...")
        self.client.reset()
        self.collections = {}


class ConversationVectorStore(VectorStore):
    """Specialized vector store for conversations."""
    
    def add_conversation(self, conversation: Dict[str, Any]):
        """Add a single conversation to the vector store."""
        from data_processors.base_processor import Conversation
        
        # If it's a Conversation object, convert to dict
        if hasattr(conversation, 'to_dict'):
            conversation = conversation.to_dict()
        
        # Chunk the conversation text
        full_text = self._conversation_to_text(conversation)
        chunks = self.embedding_generator.chunk_text(full_text)
        
        # Prepare metadata for each chunk
        metadatas = []
        chunk_ids = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{conversation['conversation_id']}_chunk_{i}"
            chunk_ids.append(chunk_id)
            
            metadatas.append({
                'conversation_id': conversation['conversation_id'],
                'platform': conversation['platform'],
                'title': conversation['title'],
                'chunk_index': i,
                'total_chunks': len(chunks),
                'created_at': conversation.get('created_at', ''),
            })
        
        # Add to conversations collection
        self.add_documents(
            collection_name=settings.conversations_collection,
            texts=chunks,
            metadatas=metadatas,
            ids=chunk_ids
        )
    
    def add_code_snippet(self, snippet: Dict[str, Any]):
        """Add a code snippet to the code collection."""
        text = f"Language: {snippet['language']}\nContext: {snippet['context']}\n\nCode:\n{snippet['code']}"
        
        metadata = {
            'language': snippet['language'],
            'source_conversation_id': snippet['source_conversation_id'],
            'platform': snippet['platform'],
            'context': snippet['context']
        }
        
        self.add_documents(
            collection_name=settings.code_collection,
            texts=[text],
            metadatas= [metadata],
            ids=[str(uuid.uuid4())]
        )
    
    def _conversation_to_text(self, conversation: Dict[str, Any]) -> str:
        """Convert conversation to searchable text."""
        lines = [
            f"Title: {conversation['title']}",
            f"Platform: {conversation['platform']}",
            ""
        ]
        
        for msg in conversation['messages']:
            role = msg['role'].upper()
            content = msg['content']
            lines.append(f"{role}: {content}")
            lines.append("")
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Test the vector store
    vector_store = ConversationVectorStore()
    
    print(f"Collections: {vector_store.list_collections()}")
    
    # Test query
    if vector_store.get_collection_count(settings.conversations_collection) > 0:
        results = vector_store.query(
            collection_name=settings.conversations_collection,
            query_text="How to implement authentication?",
            n_results=3
        )
        
        print(f"\nFound {len(results['documents'])} results")
        for i, (doc, meta, dist) in enumerate(zip(results['documents'], results['metadatas'], results['distances'])):
            print(f"\n--- Result {i+1} (distance: {dist:.3f}) ---")
            print(f"Title: {meta.get('title')}")
            print(f"Platform: {meta.get('platform')}")
            print(f"Preview: {doc[:200]}...")
