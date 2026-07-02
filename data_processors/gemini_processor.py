"""
Gemini conversation processor.
Processes Google Takeout exports or HTML saves.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup
from data_processors.base_processor import (
    BaseProcessor, Conversation, Message, MessageRole, Platform
)
from utils.logger import logger


class GeminiProcessor(BaseProcessor):
    """Process Gemini conversation exports."""
    
    def __init__(self):
        super().__init__(Platform.GEMINI)
    
    def process(self, input_path: Path) -> List[Conversation]:
        """
        Process Gemini exports (Google Takeout or HTML).
        
        Args:
            input_path: Path to Gemini export directory or HTML file
            
        Returns:
            List of standardized conversations
        """
        logger.info(f"Processing Gemini export from: {input_path}")
        
        if input_path.is_file():
            # Single HTML file
            if input_path.suffix == '.html':
                conversation = self._process_html_file(input_path)
                if conversation:
                    self.conversations.append(conversation)
                    snippets = self.extract_code_snippets(conversation)
                    self.code_snippets.extend(snippets)
            elif input_path.suffix == '.json':
                # JSON export (if available)
                conversation = self._process_json_file(input_path)
                if conversation:
                    self.conversations.append(conversation)
                    snippets = self.extract_code_snippets(conversation)
                    self.code_snippets.extend(snippets)
        else:
            # Directory with multiple files
            html_files = list(input_path.rglob("*.html"))
            json_files = list(input_path.rglob("*.json"))
            
            logger.info(f"Found {len(html_files)} HTML files, {len(json_files)} JSON files")
            
            for html_file in html_files:
                conversation = self._process_html_file(html_file)
                if conversation:
                    self.conversations.append(conversation)
                    snippets = self.extract_code_snippets(conversation)
                    self.code_snippets.extend(snippets)
            
            for json_file in json_files:
                # Skip manifests and metadata
                if any(skip in json_file.name.lower() for skip in ['manifest', 'metadata']):
                    continue
                conversation = self._process_json_file(json_file)
                if conversation:
                    self.conversations.append(conversation)
                    snippets = self.extract_code_snippets(conversation)
                    self.code_snippets.extend(snippets)
        
        logger.info(f"Processed {len(self.conversations)} conversations, {len(self.code_snippets)} code snippets")
        return self.conversations
    
    def _process_html_file(self, html_file: Path) -> Conversation:
        """Process a single HTML conversation file."""
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
            
            # Extract title (attempt multiple selectors)
            title = "Untitled Conversation"
            title_elem = soup.find('h1') or soup.find('title')
            if title_elem:
                title = title_elem.get_text().strip()[:100]
            
            # Extract messages (this will vary based on Gemini's HTML structure)
            messages = []
            
            # Try to find conversation container
            # Gemini uses various class names, adapt as needed
            message_containers = soup.find_all(['div', 'article'], class_=lambda x: x and ('message' in x.lower() or 'response' in x.lower()))
            
            if not message_containers:
                # Fallback: look for alternating user/assistant patterns
                message_containers = soup.find_all(['p', 'div'], recursive=True)
            
            current_role = MessageRole.USER
            for container in message_containers:
                text = container.get_text(separator='\n', strip=True)
                
                if not text or len(text) < 5:
                    continue
                
                # Try to detect role from classes or structure
                classes = container.get('class', [])
                role = current_role
                
                if any('user' in str(c).lower() for c in classes):
                    role = MessageRole.USER
                elif any('assistant' in str(c).lower() or 'model' in str(c).lower() or 'gemini' in str(c).lower() for c in classes):
                    role = MessageRole.ASSISTANT
                
                messages.append(Message(
                    role=role,
                    content=text,
                    timestamp=None
                ))
                
                # Alternate for next message
                current_role = MessageRole.ASSISTANT if role == MessageRole.USER else MessageRole.USER
            
            if not messages:
                logger.warning(f"No messages found in {html_file.name}")
                return None
            
            # Use file modification time as created_at
            created_at = datetime.fromtimestamp(html_file.stat().st_mtime)
            
            return Conversation(
                conversation_id=html_file.stem,
                platform=Platform.GEMINI,
                title=title,
                messages=messages,
                created_at=created_at,
                metadata={'source_file': html_file.name}
            )
            
        except Exception as e:
            logger.error(f"Error processing HTML file {html_file.name}: {e}")
            return None
    
    def _process_json_file(self, json_file: Path) -> Conversation:
        """Process a single JSON conversation file."""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            conversation_id = data.get('id', json_file.stem)
            title = data.get('title', data.get('name', 'Untitled Conversation'))
            
            # Parse timestamps
            created_at = None
            if 'created_at' in data:
                created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            
            # Parse messages
            messages = []
            messages_data = data.get('messages', data.get('history', []))
            
            for msg_data in messages_data:
                role_str = msg_data.get('role', msg_data.get('author', 'user'))
                role = MessageRole.USER if role_str.lower() == 'user' else MessageRole.ASSISTANT
                
                content = msg_data.get('content', msg_data.get('text', ''))
                
                if content:
                    messages.append(Message(
                        role=role,
                        content=content,
                        timestamp=created_at
                    ))
            
            if not messages:
                return None
            
            return Conversation(
                conversation_id=conversation_id,
                platform=Platform.GEMINI,
                title=title,
                messages=messages,
                created_at=created_at,
                metadata=data.get('metadata', {})
            )
            
        except Exception as e:
            logger.error(f"Error processing JSON file {json_file.name}: {e}")
            return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python gemini_processor.py <path_to_gemini_export>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_dir = Path("./data/processed")
    
    processor = GeminiProcessor()
    processor.process(input_path)
    processor.save_processed_data(output_dir)
    
    print(f"✓ Processed {len(processor.conversations)} conversations")
    print(f"✓ Extracted {len(processor.code_snippets)} code snippets")
    print(f"✓ Saved to {output_dir}")
