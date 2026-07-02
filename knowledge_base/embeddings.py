"""
Embedding generation utilities for the knowledge base.
Handles batch embedding creation with caching.
"""

import hashlib
import json
from pathlib import Path
from typing import List, Dict
try:
    import google.generativeai as genai
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    
from config.settings import settings
from utils.logger import logger
import tiktoken


class EmbeddingGenerator:
    """Generate and cache embeddings for text chunks using Google Gemini."""
    
    def __init__(self, model: str = None):
        """
        Initialize embedding generator.
        
        Args:
            model: Embedding model to use (defaults to settings.embedding_model)
        """
        self.model = model or settings.embedding_model
        
        # Determine provider based on model name
        is_openai_model = "text-embedding-3" in self.model or "text-embedding-ada" in self.model
        
        if is_openai_model:
            self.use_google = False
        else:
            self.use_google = GOOGLE_AVAILABLE and settings.google_api_key
        self.client = None
        self.cache_dir = settings.get_base_path() / "data" / "embeddings_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize tokenizer for chunk size estimation
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except:
            self.tokenizer = None
        
        provider = "Google Gemini" if self.use_google else "OpenAI (fallback)"
        logger.info(f"Initialized embedding generator with {provider}, model: {self.model}")
    
    def _init_client(self):
        """Lazy initialize Google Gemini or OpenAI client."""
        if not self.client:
            if self.use_google:
                # Use Google Gemini
                if not settings.google_api_key:
                    raise ValueError("Google API key not configured. Please set GOOGLE_API_KEY in .env file")
                genai.configure(api_key=settings.google_api_key)
                self.client = "gemini"  # Flag indicating Google client is configured
                logger.info("Using Google Gemini for embeddings")
            elif OPENAI_AVAILABLE:
                # Fallback to OpenAI
                if not settings.openai_api_key:
                    raise ValueError("No API keys configured. Please set GOOGLE_API_KEY or OPENAI_API_KEY in .env file")
                self.client = OpenAI(api_key=settings.openai_api_key)
                logger.info("Falling back to OpenAI for embeddings")
            else:
                raise ValueError("No embedding providers available. Install google-generativeai or openai package.")
    
    
    def generate_embeddings(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            use_cache: Whether to use cached embeddings
            
        Returns:
            List of embedding vectors
        """
        self._init_client()
        
        embeddings = []
        texts_to_embed = []
        text_indices = []
        
        # Check cache
        for i, text in enumerate(texts):
            if use_cache:
                cached_embedding = self._get_cached_embedding(text)
                if cached_embedding:
                    embeddings.append(cached_embedding)
                    continue
            
            # Need to generate this embedding
            texts_to_embed.append(text)
            text_indices.append(i)
            embeddings.append(None)  # Placeholder
        
        # Generate missing embeddings in batch
        if texts_to_embed:
            logger.info(f"Generating {len(texts_to_embed)} embeddings ({len(texts) - len(texts_to_embed)} cached)")
            
            try:
                if self.use_google and self.client == "gemini":
                    # Use Google Gemini
                    for idx, text in enumerate(texts_to_embed):
                        result = genai.embed_content(
                            model=self.model,
                            content=text,
                            task_type="retrieval_document"
                        )
                        embedding = result['embedding']
                        original_idx = text_indices[idx]
                        embeddings[original_idx] = embedding
                        
                        # Cache the embedding
                        if use_cache:
                            self._cache_embedding(text, embedding)
                else:
                    # Use OpenAI fallback
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=texts_to_embed
                    )
                    
                    # Insert generated embeddings at correct positions
                    for idx, embedding_obj in enumerate(response.data):
                        original_idx = text_indices[idx]
                        embedding = embedding_obj.embedding
                        embeddings[original_idx] = embedding
                        
                        # Cache the embedding
                        if use_cache:
                            self._cache_embedding(texts_to_embed[idx], embedding)
                
            except Exception as e:
                logger.error(f"Error generating embeddings: {e}")
                raise
        
        return embeddings
    
    def generate_single_embedding(self, text: str, use_cache: bool = True) -> List[float]:
        """Generate embedding for a single text."""
        embeddings = self.generate_embeddings([text], use_cache=use_cache)
        return embeddings[0] if embeddings else None
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        # Use hash of text + model name
        content = f"{self.model}:{text}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_embedding(self, text: str) -> List[float]:
        """Retrieve cached embedding if available."""
        cache_key = self._get_cache_key(text)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    return data['embedding']
            except Exception as e:
                logger.warning(f"Error reading cache: {e}")
        
        return None
    
    def _cache_embedding(self, text: str, embedding: List[float]):
        """Cache an embedding."""
        cache_key = self._get_cache_key(text)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'text_preview': text[:100],
                    'embedding': embedding,
                    'model': self.model
                }, f)
        except Exception as e:
            logger.warning(f"Error writing cache: {e}")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        try:
            return len(self.tokenizer.encode(text))
        except:
            # Rough estimate: 1 token ≈ 4 characters
            return len(text) // 4
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """
        Split text into chunks.
        
        Args:
            text: Text to chunk
            chunk_size: Maximum tokens per chunk (defaults to settings)
            overlap: Overlap between chunks (defaults to settings)
            
        Returns:
            List of text chunks
        """
        chunk_size = chunk_size or settings.chunk_size
        overlap = overlap or settings.chunk_overlap
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = self.count_tokens(para)
            
            if current_tokens + para_tokens > chunk_size and current_chunk:
                # Save current chunk
                chunks.append('\n\n'.join(current_chunk))
                
                # Start new chunk with overlap
                overlap_paras = []
                overlap_tokens = 0
                for p in reversed(current_chunk):
                    p_tokens = self.count_tokens(p)
                    if overlap_tokens + p_tokens <= overlap:
                        overlap_paras.insert(0, p)
                        overlap_tokens += p_tokens
                    else:
                        break
                
                current_chunk = overlap_paras
                current_tokens = overlap_tokens
            
            current_chunk.append(para)
            current_tokens += para_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks
