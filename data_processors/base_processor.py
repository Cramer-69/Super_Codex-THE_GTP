"""
Base data processor with common schemas and utilities.
All platform-specific processors inherit from this base.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from enum import Enum


class MessageRole(str, Enum):
    """Message role in a conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Platform(str, Enum):
    """Supported AI platforms."""
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    GROK = "grok"
    ANTIGRAVITY = "antigravity"


@dataclass
class Message:
    """Standardized message format."""
    role: MessageRole
    content: str
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata
        }


@dataclass
class Conversation:
    """Standardized conversation format."""
    conversation_id: str
    platform: Platform
    title: str
    messages: List[Message]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "conversation_id": self.conversation_id,
            "platform": self.platform.value,
            "title": self.title,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata
        }
    
    def get_text(self) -> str:
        """Get full conversation as text."""
        lines = [f"Title: {self.title}", f"Platform: {self.platform.value}", ""]
        for msg in self.messages:
            lines.append(f"{msg.role.value.upper()}: {msg.content}")
            lines.append("")
        return "\n".join(lines)


@dataclass
class CodeSnippet:
    """Extracted code snippet."""
    code: str
    language: str
    context: str
    source_conversation_id: str
    platform: Platform
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "language": self.language,
            "context": self.context,
            "source_conversation_id": self.source_conversation_id,
            "platform": self.platform.value,
            "metadata": self.metadata
        }


class BaseProcessor(ABC):
    """Base class for platform-specific data processors."""
    
    def __init__(self, platform: Platform):
        self.platform = platform
        self.conversations: List[Conversation] = []
        self.code_snippets: List[CodeSnippet] = []
    
    @abstractmethod
    def process(self, input_path: Path) -> List[Conversation]:
        """
        Process platform-specific export data.
        
        Args:
            input_path: Path to export file or directory
            
        Returns:
            List of standardized conversations
        """
        pass
    
    def extract_code_snippets(self, conversation: Conversation) -> List[CodeSnippet]:
        """
        Extract code snippets from conversation messages.
        
        Args:
            conversation: Conversation to extract from
            
        Returns:
            List of code snippets
        """
        snippets = []
        
        for msg in conversation.messages:
            # Simple markdown code block detection
            import re
            pattern = r'```(\w+)?\n(.*?)```'
            matches = re.findall(pattern, msg.content, re.DOTALL)
            
            for language, code in matches:
                snippets.append(CodeSnippet(
                    code=code.strip(),
                    language=language or "unknown",
                    context=f"From: {conversation.title}",
                    source_conversation_id=conversation.conversation_id,
                    platform=self.platform
                ))
        
        return snippets
    
    def save_processed_data(self, output_dir: Path):
        """
        Save processed conversations and code snippets.
        
        Args:
            output_dir: Directory to save processed data
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save conversations
        conversations_file = output_dir / f"{self.platform.value}_conversations.json"
        with open(conversations_file, 'w', encoding='utf-8') as f:
            json.dump(
                [conv.to_dict() for conv in self.conversations],
                f,
                indent=2,
                ensure_ascii=False
            )
        
        # Save code snippets
        if self.code_snippets:
            snippets_file = output_dir / f"{self.platform.value}_code_snippets.json"
            with open(snippets_file, 'w', encoding='utf-8') as f:
                json.dump(
                    [snippet.to_dict() for snippet in self.code_snippets],
                    f,
                    indent=2,
                    ensure_ascii=False
                )
        
        return conversations_file
