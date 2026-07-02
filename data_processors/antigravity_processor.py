"""
Antigravity conversation processor.
Processes Antigravity conversation logs and artifacts from the brain directory.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List
from data_processors.base_processor import (
    BaseProcessor, Conversation, Message, MessageRole, Platform
)
from utils.logger import logger


class AntigravityProcessor(BaseProcessor):
    """Process Antigravity conversation logs and artifacts."""
    
    def __init__(self):
        super().__init__(Platform.ANTIGRAVITY)
    
    def process(self, input_path: Path) -> List[Conversation]:
        """
        Process Antigravity brain directory with conversation logs.
        
        Args:
            input_path: Path to antigravity brain directory
            
        Returns:
            List of standardized conversations
        """
        logger.info(f"Processing Antigravity conversations from: {input_path}")
        
        if not input_path.exists():
            logger.error(f"Directory not found: {input_path}")
            return []
        
        # Find all conversation directories (UUID format)
        conversation_dirs = [d for d in input_path.iterdir() if d.is_dir() and len(d.name) > 30]
        
        logger.info(f"Found {len(conversation_dirs)} conversation directories")
        
        for conv_dir in conversation_dirs:
            try:
                conversation = self._process_conversation_dir(conv_dir)
                if conversation:
                    self.conversations.append(conversation)
                    # Extract code snippets
                    snippets = self.extract_code_snippets(conversation)
                    self.code_snippets.extend(snippets)
            except Exception as e:
                logger.warning(f"Error processing {conv_dir.name}: {e}")
                continue
        
        logger.info(f"Processed {len(self.conversations)} conversations, {len(self.code_snippets)} code snippets")
        return self.conversations
    
    def _process_conversation_dir(self, conv_dir: Path) -> Conversation:
        """Process a single conversation directory."""
        conversation_id = conv_dir.name
        
        # Read artifacts and logs
        artifacts_dir = conv_dir
        system_logs_dir = conv_dir / ".system_generated" / "logs"
        
        # Try to get title from task.md or implementation_plan.md
        title = "Untitled Conversation"
        task_file = artifacts_dir / "task.md"
        plan_file = artifacts_dir / "implementation_plan.md"
        
        if task_file.exists():
            with open(task_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith('#'):
                    title = first_line.lstrip('#').strip()[:100]
        elif plan_file.exists():
            with open(plan_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith('#'):
                    title = first_line.lstrip('#').strip()[:100]
        
        # Parse messages from overview and task logs
        messages = []
        
        if system_logs_dir.exists():
            # Read overview.txt
            overview_file = system_logs_dir / "overview.txt"
            if overview_file.exists():
                messages.extend(self._parse_overview_file(overview_file))
            
            # Read task log files
            task_logs = sorted(system_logs_dir.glob("task_*.txt"))
            for task_log in task_logs:
                messages.extend(self._parse_task_log(task_log))
        
        # Add artifacts as context messages
        artifact_files = [
            artifacts_dir / "task.md",
            artifacts_dir / "implementation_plan.md",
            artifacts_dir / "walkthrough.md"
        ]
        
        for artifact_file in artifact_files:
            if artifact_file.exists():
                with open(artifact_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        messages.append(Message(
                            role=MessageRole.ASSISTANT,
                            content=f"[Artifact: {artifact_file.name}]\n\n{content}",
                            metadata={'artifact': True, 'filename': artifact_file.name}
                        ))
        
        if not messages:
            logger.warning(f"No messages found for conversation {conversation_id}")
            return None
        
        # Get timestamps from directory
        created_at = datetime.fromtimestamp(conv_dir.stat().st_ctime)
        updated_at = datetime.fromtimestamp(conv_dir.stat().st_mtime)
        
        return Conversation(
            conversation_id=conversation_id,
            platform=Platform.ANTIGRAVITY,
            title=title,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
            metadata={'artifacts_dir': str(artifacts_dir)}
        )
    
    def _parse_overview_file(self, overview_file: Path) -> List[Message]:
        """Parse the overview.txt file."""
        messages = []
        
        try:
            with open(overview_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by USER_REQUEST and ASSISTANT sections
            sections = content.split('USER_REQUEST:')
            
            for section in sections[1:]:  # Skip first empty section
                if 'ASSISTANT:' in section:
                    user_part, assistant_part = section.split('ASSISTANT:', 1)
                    
                    user_text = user_part.strip()
                    if user_text:
                        messages.append(Message(
                            role=MessageRole.USER,
                            content=user_text
                        ))
                    
                    assistant_text = assistant_part.strip()
                    if assistant_text:
                        messages.append(Message(
                            role=MessageRole.ASSISTANT,
                            content=assistant_text
                        ))
                else:
                    # Just user request
                    user_text = section.strip()
                    if user_text:
                        messages.append(Message(
                            role=MessageRole.USER,
                            content=user_text
                        ))
        
        except Exception as e:
            logger.error(f"Error parsing overview file: {e}")
        
        return messages
    
    def _parse_task_log(self, task_log: Path) -> List[Message]:
        """Parse a task log file."""
        messages = []
        
        try:
            with open(task_log, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Task logs contain detailed execution info
            if content.strip():
                messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=f"[Task Log: {task_log.name}]\n\n{content}",
                    metadata={'task_log': True, 'filename': task_log.name}
                ))
        
        except Exception as e:
            logger.error(f"Error parsing task log: {e}")
        
        return messages


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python antigravity_processor.py <path_to_brain_directory>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_dir = Path("./data/processed")
    
    processor = AntigravityProcessor()
    processor.process(input_path)
    processor.save_processed_data(output_dir)
    
    print(f"✓ Processed {len(processor.conversations)} conversations")
    print(f"✓ Extracted {len(processor.code_snippets)} code snippets")
    print(f"✓ Saved to {output_dir}")
