"""
Main data ingestion script.
Processes all platform exports and loads them into the vector store.
"""

import sys
import io

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import argparse
from pathlib import Path
from data_processors.chatgpt_processor import ChatGPTProcessor
from data_processors.gemini_processor import GeminiProcessor
from data_processors.grok_processor import GrokProcessor
from data_processors.antigravity_processor import AntigravityProcessor
from knowledge_base.vector_store import ConversationVectorStore
from config.settings import settings
from utils.logger import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def ingest_data(
    chatgpt_path: Path = None,
    gemini_path: Path = None,
    grok_path: Path = None,
    antigravity_path: Path = None,
    reset_db: bool = False
):
    """
    Ingest data from all platforms into the vector store.
    
    Args:
        chatgpt_path: Path to ChatGPT export
        gemini_path: Path to Gemini export
        grok_path: Path to Grok export
        antigravity_path: Path to Antigravity brain directory
        reset_db: Whether to reset the database before ingesting
    """
    console.print("\n[bold blue]🚀 Conductor Agent - Data Ingestion[/bold blue]\n")
    
    # Initialize vector store
    vector_store = ConversationVectorStore()
    
    if reset_db:
        console.print("[yellow]⚠️  Resetting database...[/yellow]")
        vector_store.reset()
    
    all_conversations = []
    all_code_snippets = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        # Process ChatGPT
        if chatgpt_path and chatgpt_path.exists():
            task = progress.add_task("[cyan]Processing ChatGPT export...", total=None)
            processor = ChatGPTProcessor()
            conversations = processor.process(chatgpt_path)
            all_conversations.extend(processor.conversations)
            all_code_snippets.extend(processor.code_snippets)
            progress.update(task, completed=True)
            console.print(f"✓ ChatGPT: {len(conversations)} conversations, {len(processor.code_snippets)} code snippets")
        
        # Process Gemini
        if gemini_path and gemini_path.exists():
            task = progress.add_task("[cyan]Processing Gemini export...", total=None)
            processor = GeminiProcessor()
            conversations = processor.process(gemini_path)
            all_conversations.extend(processor.conversations)
            all_code_snippets.extend(processor.code_snippets)
            progress.update(task, completed=True)
            console.print(f"✓ Gemini: {len(conversations)} conversations, {len(processor.code_snippets)} code snippets")
        
        # Process Grok
        if grok_path and grok_path.exists():
            task = progress.add_task("[cyan]Processing Grok export...", total=None)
            processor = GrokProcessor()
            conversations = processor.process(grok_path)
            all_conversations.extend(processor.conversations)
            all_code_snippets.extend(processor.code_snippets)
            progress.update(task, completed=True)
            console.print(f"✓ Grok: {len(conversations)} conversations, {len(processor.code_snippets)} code snippets")
        
        # Process Antigravity
        if antigravity_path and antigravity_path.exists():
            task = progress.add_task("[cyan]Processing Antigravity conversations...", total=None)
            processor = AntigravityProcessor()
            conversations = processor.process(antigravity_path)
            all_conversations.extend(processor.conversations)
            all_code_snippets.extend(processor.code_snippets)
            progress.update(task, completed=True)
            console.print(f"✓ Antigravity: {len(conversations)} conversations, {len(processor.code_snippets)} code snippets")
    
    # Add to vector store
    console.print(f"\n[bold green]📊 Total: {len(all_conversations)} conversations, {len(all_code_snippets)} code snippets[/bold green]\n")
    
    if all_conversations:
        console.print("[cyan]Adding conversations to vector store...[/cyan]")
        for conv in all_conversations:
            vector_store.add_conversation(conv.to_dict() if hasattr(conv, 'to_dict') else conv)
        console.print(f"✓ Added {len(all_conversations)} conversations")
    
    if all_code_snippets:
        console.print("[cyan]Adding code snippets to vector store...[/cyan]")
        for snippet in all_code_snippets:
            vector_store.add_code_snippet(snippet.to_dict() if hasattr(snippet, 'to_dict') else snippet)
        console.print(f"✓ Added {len(all_code_snippets)} code snippets")
    
    # Show statistics
    console.print("\n[bold green]✅ Ingestion Complete![/bold green]\n")
    console.print(f"Conversations in DB: {vector_store.get_collection_count(settings.conversations_collection)}")
    console.print(f"Code snippets in DB: {vector_store.get_collection_count(settings.code_collection)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest conversation data into conductor agent")
    parser.add_argument("--chatgpt", type=Path, help="Path to ChatGPT export (conversations.json or ZIP)")
    parser.add_argument("--gemini", type=Path, help="Path to Gemini export (directory or HTML)")
    parser.add_argument("--grok", type=Path, help="Path to Grok export (ZIP)")
    parser.add_argument("--antigravity", type=Path, help="Path to Antigravity brain directory")
    parser.add_argument("--reset", action="store_true", help="Reset database before ingesting")
    
    args = parser.parse_args()
    
    # Use defaults from settings if not provided
    if not any([args.chatgpt, args.gemini, args.grok, args.antigravity]):
        # Default to Antigravity brain directory
        args.antigravity = Path(settings.antigravity_brain_dir)
    
    ingest_data(
        chatgpt_path=args.chatgpt,
        gemini_path=args.gemini,
        grok_path=args.grok,
        antigravity_path=args.antigravity,
        reset_db=args.reset
    )
