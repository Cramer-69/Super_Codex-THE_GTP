"""
ChatGPT conversation processor.
Processes ChatGPT data export (conversations.json).
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List
from data_processors.base_processor import (
    BaseProcessor, Conversation, Message, MessageRole, Platform
)
from utils.logger import logger


class ChatGPTProcessor(BaseProcessor):
    """Process ChatGPT conversation exports."""
    
    def __init__(self):
        super().__init__(Platform.CHATGPT)
    
    def process(self, input_path: Path) -> List[Conversation]:
        """
        Process ChatGPT conversations.json export.
        
        Args:
            input_path: Path to conversations.json or parent ZIP
            
        Returns:
            List of standardized conversations
        """
        logger.info(f"Processing ChatGPT export from: {input_path}")
        
        # Handle both direct JSON and ZIP files
        if input_path.suffix == '.zip':
            import zipfile
            with zipfile.ZipFile(input_path, 'r') as zip_ref:
                # Extract conversations.json
                conversations_data = zip_ref.read('conversations.json')
                data = json.loads(conversations_data)
        else:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # ChatGPT export is a list of conversation objects
        if isinstance(data, list):
            conversations = data
        else:
            # Sometimes it's wrapped in an object
            conversations = data.get('conversations', data)
        
        logger.info(f"Found {len(conversations)} conversations")
        
        for conv_data in conversations:
            conversation = self._parse_conversation(conv_data)
            if conversation:
                self.conversations.append(conversation)
                # Extract code snippets
                snippets = self.extract_code_snippets(conversation)
                self.code_snippets.extend(snippets)
        
        logger.info(f"Processed {len(self.conversations)} conversations, {len(self.code_snippets)} code snippets")
        return self.conversations
    
    def _parse_conversation(self, conv_data: dict) -> Conversation:
        """Parse a single conversation from ChatGPT format."""
        try:
            conversation_id = conv_data.get('id', conv_data.get('conversation_id', ''))
            title = conv_data.get('title', 'Untitled Conversation')
            
            # Parse timestamp
            created_at = None
            if 'create_time' in conv_data:
                created_at = datetime.fromtimestamp(conv_data['create_time'])
            elif 'created' in conv_data:
                created_at = datetime.fromtimestamp(conv_data['created'])
            
            updated_at = None
            if 'update_time' in conv_data:
                updated_at = datetime.fromtimestamp(conv_data['update_time'])
            
            # Parse messages
            messages = []
            mapping = conv_data.get('mapping', {})
            
            # ChatGPT uses a tree structure, we need to traverse it
            message_nodes = []
            for node_id, node in mapping.items():
                if node.get('message'):
                    message_nodes.append(node['message'])
            
            # Sort by create_time
            message_nodes.sort(key=lambda x: x.get('create_time', 0))
            
            for msg_data in message_nodes:
                msg = self._parse_message(msg_data)
                if msg:
                    messages.append(msg)
            
            return Conversation(
                conversation_id=conversation_id,
                platform=Platform.CHATGPT,
                title=title,
                messages=messages,
                created_at=created_at,
                updated_at=updated_at,
                metadata={
                    'model': conv_data.get('model'),
                    'plugin_ids': conv_data.get('plugin_ids', [])
                }
            )
        except Exception as e:
            logger.error(f"Error parsing conversation: {e}")
            return None
    
    def _parse_message(self, msg_data: dict) -> Message:
        """Parse a single message from ChatGPT format."""
        try:
            author_role = msg_data.get('author', {}).get('role', '')
            
            # Map ChatGPT roles to standard roles
            role_mapping = {
                'user': MessageRole.USER,
                'assistant': MessageRole.ASSISTANT,
                'system': MessageRole.SYSTEM
            }
            role = role_mapping.get(author_role, MessageRole.SYSTEM)
            
            # Extract content
            content_parts = msg_data.get('content', {}).get('parts', [])
            content = '\n'.join(str(part) for part in content_parts if part)
            
            if not content:
                return None
            
            # Parse timestamp
            timestamp = None
            if 'create_time' in msg_data:
                timestamp = datetime.fromtimestamp(msg_data['create_time'])
            
            return Message(
                role=role,
                content=content,
                timestamp=timestamp,
                metadata={
                    'message_id': msg_data.get('id'),
                    'model': msg_data.get('metadata', {}).get('model_slug'),
                    'weight': msg_data.get('weight')
                }
            )
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None


if __name__ == "__main__":
    # Test the processor
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python chatgpt_processor.py <path_to_conversations.json>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_dir = Path("./data/processed")
    
    processor = ChatGPTProcessor()
    processor.process(input_path)
    processor.save_processed_data(output_dir)
    
    print(f"✓ Processed {len(processor.conversations)} conversations")
    print(f"✓ Extracted {len(processor.code_snippets)} code snippets")
    print(f"✓ Saved to {output_dir}")
