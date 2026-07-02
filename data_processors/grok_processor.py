"""
Grok/xAI conversation processor.
Extends the SuperGrok workflow from user rules.
"""

import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List
from data_processors.base_processor import (
    BaseProcessor, Conversation, Message, MessageRole, Platform
)
from utils.logger import logger


class GrokProcessor(BaseProcessor):
    """Process Grok/xAI conversation exports."""
    
    def __init__(self):
        super().__init__(Platform.GROK)
    
    def process(self, input_path: Path) -> List[Conversation]:
        """
        Process Grok ZIP export with JSON conversation files.
        
        Args:
            input_path: Path to Grok export ZIP file
            
        Returns:
            List of standardized conversations
        """
        logger.info(f"Processing Grok export from: {input_path}")
        
        if not input_path.exists():
            logger.error(f"File not found: {input_path}")
            return []
        
        # Extract ZIP file
        extract_dir = input_path.parent / f"grok_extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        extract_dir.mkdir(exist_ok=True)
        
        with zipfile.ZipFile(input_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        logger.info(f"Extracted to: {extract_dir}")
        
        # Find all JSON conversation files
        json_files = list(extract_dir.rglob("*.json"))
        logger.info(f"Found {len(json_files)} JSON files")
        
        for json_file in json_files:
            try:
                # Skip system/metadata files
                if any(skip in json_file.name.lower() for skip in ['manifest', 'metadata', 'account']):
                    continue
                
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                conversation = self._parse_conversation(data, json_file.name)
                if conversation:
                    self.conversations.append(conversation)
                    # Extract code snippets
                    snippets = self.extract_code_snippets(conversation)
                    self.code_snippets.extend(snippets)
                    
            except Exception as e:
                logger.warning(f"Error processing {json_file.name}: {e}")
                continue
        
        logger.info(f"Processed {len(self.conversations)} conversations, {len(self.code_snippets)} code snippets")
        return self.conversations
    
    def _parse_conversation(self, data: dict, filename: str) -> Conversation:
        """Parse a single Grok conversation."""
        try:
            # Grok format may vary, adapt as needed
            conversation_id = data.get('id', data.get('conversation_id', filename))
            
            # Try different title fields
            title = (
                data.get('title') or 
                data.get('name') or 
                data.get('prompt', '')[:50] or 
                'Untitled Conversation'
            )
            
            # Parse timestamps
            created_at = None
            updated_at = None
            
            if 'created_at' in data:
                created_at = self._parse_timestamp(data['created_at'])
            elif 'timestamp' in data:
                created_at = self._parse_timestamp(data['timestamp'])
            
            if 'updated_at' in data:
                updated_at = self._parse_timestamp(data['updated_at'])
            
            # Parse messages
            messages = []
            
            # Try different message field names
            messages_data = (
                data.get('messages', []) or 
                data.get('history', []) or 
                data.get('chat', [])
            )
            
            for msg_data in messages_data:
                msg = self._parse_message(msg_data)
                if msg:
                    messages.append(msg)
            
            # If no messages found in array format, try conversation format
            if not messages and 'prompt' in data and 'response' in data:
                messages.append(Message(
                    role=MessageRole.USER,
                    content=data['prompt'],
                    timestamp=created_at
                ))
                messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=data['response'],
                    timestamp=created_at
                ))
            
            if not messages:
                return None
            
            return Conversation(
                conversation_id=conversation_id,
                platform=Platform.GROK,
                title=title,
                messages=messages,
                created_at=created_at,
                updated_at=updated_at,
                metadata=data.get('metadata', {})
            )
            
        except Exception as e:
            logger.error(f"Error parsing Grok conversation: {e}")
            return None
    
    def _parse_message(self, msg_data: dict) -> Message:
        """Parse a single Grok message."""
        try:
            # Determine role
            role_str = msg_data.get('role', msg_data.get('sender', msg_data.get('type', 'user')))
            
            role_mapping = {
                'user': MessageRole.USER,
                'human': MessageRole.USER,
                'assistant': MessageRole.ASSISTANT,
                'ai': MessageRole.ASSISTANT,
                'grok': MessageRole.ASSISTANT,
                'system': MessageRole.SYSTEM
            }
            role = role_mapping.get(role_str.lower(), MessageRole.USER)
            
            # Extract content
            content = (
                msg_data.get('content') or 
                msg_data.get('text') or 
                msg_data.get('message') or
                str(msg_data.get('data', ''))
            )
            
            if not content:
                return None
            
            # Parse timestamp
            timestamp = None
            if 'timestamp' in msg_data:
                timestamp = self._parse_timestamp(msg_data['timestamp'])
            elif 'created_at' in msg_data:
                timestamp = self._parse_timestamp(msg_data['created_at'])
            
            return Message(
                role=role,
                content=content,
                timestamp=timestamp,
                metadata={}
            )
            
        except Exception as e:
            logger.error(f"Error parsing Grok message: {e}")
            return None
    
    def _parse_timestamp(self, ts) -> datetime:
        """Parse various timestamp formats."""
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts)
        elif isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                return datetime.now()
        return datetime.now()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python grok_processor.py <path_to_grok_export.zip>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_dir = Path("./data/processed")
    
    processor = GrokProcessor()
    processor.process(input_path)
    processor.save_processed_data(output_dir)
    
    print(f"✓ Processed {len(processor.conversations)} conversations")
    print(f"✓ Extracted {len(processor.code_snippets)} code snippets")
    print(f"✓ Saved to {output_dir}")
