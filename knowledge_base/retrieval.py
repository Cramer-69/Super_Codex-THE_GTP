"""
Retrieval utilities for hybrid search and re-ranking.
"""

from typing import List, Dict, Any, Optional
from knowledge_base.vector_store import ConversationVectorStore
from config.settings import settings
from utils.logger import logger


class ConversationRetriever:
    """Advanced retrieval with hybrid search and re-ranking."""
    
    def __init__(self, vector_store: ConversationVectorStore = None):
        """
        Initialize retriever.
        
        Args:
            vector_store: Vector store instance (creates new if None)
        """
        self.vector_store = vector_store or ConversationVectorStore()
    
    def search_conversations(
        self,
        query: str,
        n_results: int = None,
        platform_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search conversations with optional platform filtering.
        
        Args:
            query: Search query
            n_results: Number of results
            platform_filter: Filter by platform (e.g., "chatgpt", "gemini")
            
        Returns:
            List of search results with metadata
        """
        n_results = n_results or settings.top_k
        
        # Build metadata filter
        where = None
        if platform_filter:
            where = {"platform": platform_filter}
        
        # Query vector store
        results = self.vector_store.query(
            collection_name=settings.conversations_collection,
            query_text=query,
            n_results=n_results * 2,  # Get more for re-ranking
            where=where
        )
        
        # Format results
        formatted_results = []
        for i in range(len(results['documents'])):
            formatted_results.append({
                'content': results['documents'][i],
                'metadata': results['metadatas'][i],
                'score': 1 - results['distances'][i],  # Convert distance to similarity
                'id': results['ids'][i]
            })
        
        # Re-rank and limit
        formatted_results = self._rerank_results(formatted_results, query)
        return formatted_results[:n_results]
    
    def search_code(
        self,
        query: str,
        language_filter: Optional[str] = None,
        n_results: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search code snippets.
        
        Args:
            query: Search query
            language_filter: Filter by programming language
            n_results: Number of results
            
        Returns:
            List of code snippets with metadata
        """
        n_results = n_results or settings.top_k
        
        # Build metadata filter
        where = None
        if language_filter:
            where = {"language": language_filter}
        
        # Query vector store
        results = self.vector_store.query(
            collection_name=settings.code_collection,
            query_text=query,
            n_results=n_results,
            where=where
        )
        
        # Format results
        formatted_results = []
        for i in range(len(results['documents'])):
            formatted_results.append({
                'content': results['documents'][i],
                'metadata': results['metadatas'][i],
                'score': 1 - results['distances'][i],
                'id': results['ids'][i]
            })
        
        return formatted_results
    
    def _rerank_results(self, results: List[Dict], query: str) -> List[Dict]:
        """
        Re-rank results based on additional criteria.
        
        Args:
            results: Initial results
            query: Original query
            
        Returns:
            Re-ranked results
        """
        # Simple re-ranking: boost recent conversations
        # More sophisticated re-ranking could use a cross-encoder
        
        for result in results:
            metadata = result['metadata']
            
            # Boost based on recency
            if 'created_at' in metadata and metadata['created_at']:
                try:
                    from datetime import datetime
                    created_at = datetime.fromisoformat(metadata['created_at'].replace('Z', '+00:00'))
                    now = datetime.now(created_at.tzinfo)
                    days_old = (now - created_at).days
                    
                    # Decay factor: reduce score for older conversations
                    recency_boost = max(0, 1 - (days_old / 365))  # Decay over 1 year
                    result['score'] = result['score'] * (0.7 + 0.3 * recency_boost)
                except:
                    pass
        
        # Sort by adjusted score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
    
    def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 4000,
        platform_filter: Optional[str] = None
    ) -> str:
        """
        Get formatted context for a query.
        
        Args:
            query: User query
            max_tokens: Maximum tokens for context
            platform_filter: Optional platform filter
            
        Returns:
            Formatted context string
        """
        results = self.search_conversations(
            query=query,
            n_results=10,
            platform_filter=platform_filter
        )
        
        context_parts = []
        total_length = 0
        
        for i, result in enumerate(results):
            meta = result['metadata']
            content = result['content']
            
            # Format source citation
            source = f"[Source: {meta['platform'].upper()} - {meta['title']}]"
            formatted = f"{source}\n{content}\n"
            
            # Check token limit (rough estimate: 1 token ≈ 4 chars)
            estimated_tokens = len(formatted) // 4
            
            if total_length + estimated_tokens > max_tokens:
                break
            
            context_parts.append(formatted)
            total_length += estimated_tokens
        
        if not context_parts:
            return "No relevant context found."
        
        return "\n---\n\n".join(context_parts)


if __name__ == "__main__":
    # Test retrieval
    retriever = ConversationRetriever()
    
    results = retriever.search_conversations(
        query="authentication implementation",
        n_results=3
    )
    
    print(f"Found {len(results)} results:\n")
    for i, result in enumerate(results):
        print(f"Result {i+1} (score: {result['score']:.3f})")
        print(f"Platform: {result['metadata']['platform']}")
        print(f"Title: {result['metadata']['title']}")
        print(f"Content preview: {result['content'][:150]}...")
        print()
