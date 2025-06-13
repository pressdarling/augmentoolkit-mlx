#!/usr/bin/env python3
"""
Simple Chat Interface

A clean, user-friendly chat interface for testing your fine-tuned models.
Includes conversation history, customizable settings, and export functionality.

Usage:
    python simple_chat.py ./fine-tuned-model
    python simple_chat.py ./fine-tuned-model --system-prompt "You are a helpful coding assistant"
    python simple_chat.py ./fine-tuned-model --save-conversation chat_log.json
"""

import argparse
from pathlib import Path
import json
import time
from typing import List, Dict, Any
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

from mlx_pipeline import InferenceEngine, InferenceConfig

console = Console()

class ChatSession:
    """Manages a chat session with conversation history and settings."""
    
    def __init__(self, engine: InferenceEngine, system_prompt: str = None):
        self.engine = engine
        self.system_prompt = system_prompt or "You are a helpful AI assistant."
        self.conversation_history = []
        self.settings = {
            "temperature": 0.7,
            "max_tokens": 300,
            "top_p": 0.9,
            "include_history": True,
            "max_history_length": 10
        }
        
        # Add system message to history
        self.conversation_history.append({
            "role": "system",
            "content": self.system_prompt,
            "timestamp": time.time()
        })
    
    def format_prompt_with_history(self, user_input: str) -> str:
        """Format the current input with conversation history."""
        if not self.settings["include_history"]:
            return f"System: {self.system_prompt}\n\nUser: {user_input}\nAssistant:"
        
        # Build conversation context
        context_parts = []
        
        # Get recent history (excluding current input)
        recent_history = self.conversation_history[-self.settings["max_history_length"]:]
        
        for msg in recent_history:
            if msg["role"] == "system":
                context_parts.append(f"System: {msg['content']}")
            elif msg["role"] == "user":
                context_parts.append(f"User: {msg['content']}")
            elif msg["role"] == "assistant":
                context_parts.append(f"Assistant: {msg['content']}")
        
        # Add current user input
        context_parts.append(f"User: {user_input}")
        context_parts.append("Assistant:")
        
        return "\n\n".join(context_parts)
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
    
    def generate_response(self, user_input: str) -> Dict[str, Any]:
        """Generate a response to user input."""
        # Add user message to history
        self.add_message("user", user_input)
        
        # Format prompt with context
        formatted_prompt = self.format_prompt_with_history(user_input)
        
        # Generate response
        result = self.engine.generate_response(
            formatted_prompt,
            {
                "temperature": self.settings["temperature"],
                "max_tokens": self.settings["max_tokens"], 
                "top_p": self.settings["top_p"]
            }
        )
        
        if result["success"]:
            # Clean up response (remove any prompt repetition)
            response = result["response"]
            if response.startswith(formatted_prompt):
                response = response[len(formatted_prompt):].strip()
            
            # Add assistant response to history
            self.add_message("assistant", response)
            
            return {
                "success": True,
                "response": response,
                "metadata": result["metadata"]
            }
        else:
            return result
    
    def display_conversation(self):
        """Display the current conversation history."""
        console.print(Panel("[bold blue]Conversation History[/bold blue]", expand=False))
        
        for msg in self.conversation_history:
            if msg["role"] == "system":
                continue  # Don't display system messages in history
            
            role_color = "cyan" if msg["role"] == "user" else "green"
            role_name = "You" if msg["role"] == "user" else "Assistant"
            
            console.print(f"\n[{role_color}]{role_name}:[/{role_color}] {msg['content']}")
    
    def update_settings(self, setting: str, value: Any):
        """Update a chat setting."""
        if setting in self.settings:
            old_value = self.settings[setting]
            self.settings[setting] = value
            console.print(f"[green]Updated {setting}: {old_value} → {value}[/green]")
        else:
            console.print(f"[red]Unknown setting: {setting}[/red]")
    
    def save_conversation(self, filepath: Path):
        """Save conversation to JSON file."""
        conversation_data = {
            "timestamp": time.time(),
            "system_prompt": self.system_prompt,
            "settings": self.settings,
            "conversation": self.conversation_history,
            "message_count": len([m for m in self.conversation_history if m["role"] != "system"])
        }
        
        with open(filepath, 'w') as f:
            json.dump(conversation_data, f, indent=2)

def show_help():
    """Display help information."""
    console.print(Panel(
        "[bold]Available Commands:[/bold]\n\n"
        "• /help - Show this help message\n"
        "• /settings - Show current settings\n"
        "• /temp <value> - Set temperature (0.0-2.0)\n"
        "• /tokens <value> - Set max tokens\n"
        "• /history - Toggle conversation history\n"
        "• /clear - Clear conversation history\n"
        "• /save <filename> - Save conversation to file\n"
        "• /stats - Show performance statistics\n"
        "• /quit or /exit - End chat session\n\n"
        "[dim]Just type your message to chat normally[/dim]",
        title="Chat Commands",
        border_style="blue"
    ))

def show_settings(session: ChatSession):
    """Display current chat settings."""
    table = Table(title="Current Settings")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    for key, value in session.settings.items():
        table.add_row(key, str(value))
    
    console.print(table)

def show_stats(session: ChatSession):
    """Display session statistics."""
    stats = session.engine.get_performance_stats()
    
    table = Table(title="Session Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    # Message counts
    user_messages = len([m for m in session.conversation_history if m["role"] == "user"])
    assistant_messages = len([m for m in session.conversation_history if m["role"] == "assistant"])
    
    table.add_row("User Messages", str(user_messages))
    table.add_row("Assistant Messages", str(assistant_messages))
    table.add_row("Total Requests", str(stats.get("total_requests", 0)))
    table.add_row("Average Speed", f"{stats.get('avg_tokens_per_second', 0):.1f} tokens/sec")
    table.add_row("Current Memory", f"{stats.get('current_memory_gb', 0):.1f} GB")
    
    if "error_rate" in stats:
        table.add_row("Error Rate", f"{stats['error_rate']:.1%}")
    
    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="Simple chat interface for MLX models")
    parser.add_argument("model_path", type=Path, help="Path to the model")
    parser.add_argument("--adapter-path", type=Path, help="Path to adapter (for LoRA models)")
    parser.add_argument("--system-prompt", type=str, help="Custom system prompt")
    parser.add_argument("--temperature", type=float, default=0.7, help="Default temperature")
    parser.add_argument("--max-tokens", type=int, default=300, help="Default max tokens")
    parser.add_argument("--save-conversation", type=Path, help="Auto-save conversation to file")
    parser.add_argument("--load-conversation", type=Path, help="Load previous conversation")
    
    args = parser.parse_args()
    
    # Validate model path
    if not args.model_path.exists():
        console.print(f"[red]Model path does not exist: {args.model_path}[/red]")
        return 1
    
    # Initialize inference engine
    console.print("[blue]Loading model...[/blue]")
    
    config = InferenceConfig(
        max_tokens=args.max_tokens,
        temperature=args.temperature
    )
    
    engine = InferenceEngine(config)
    load_result = engine.load_model(args.model_path, args.adapter_path)
    
    if not load_result["success"]:
        console.print(f"[red]Failed to load model: {load_result['error']}[/red]")
        return 1
    
    console.print(f"[green]✓ Model loaded successfully[/green]")
    
    # Initialize chat session
    system_prompt = args.system_prompt
    if not system_prompt:
        # Try to infer a good system prompt based on model name
        model_name = args.model_path.name.lower()
        if "code" in model_name:
            system_prompt = "You are a helpful coding assistant. Provide clear, accurate code examples and explanations."
        elif "instruct" in model_name:
            system_prompt = "You are a helpful AI assistant. Provide informative and helpful responses."
        else:
            system_prompt = "You are a helpful AI assistant."
    
    session = ChatSession(engine, system_prompt)
    
    # Load previous conversation if requested
    if args.load_conversation and args.load_conversation.exists():
        try:
            with open(args.load_conversation, 'r') as f:
                conv_data = json.load(f)
            session.conversation_history = conv_data.get("conversation", [])
            console.print(f"[green]Loaded conversation from {args.load_conversation}[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not load conversation: {e}[/yellow]")
    
    # Welcome message
    console.print(Panel(
        f"[bold green]Chat Session Started[/bold green]\n\n"
        f"Model: {args.model_path.name}\n"
        f"System: {system_prompt[:100]}{'...' if len(system_prompt) > 100 else ''}\n\n"
        f"Type your message and press Enter to chat.\n"
        f"Type /help for available commands.",
        title="🤖 MLX Chat Interface"
    ))
    
    # Main chat loop
    try:
        while True:
            # Get user input
            user_input = Prompt.ask("\n[cyan]You[/cyan]")
            
            # Handle commands
            if user_input.startswith('/'):
                command_parts = user_input[1:].split(' ', 1)
                command = command_parts[0].lower()
                args_str = command_parts[1] if len(command_parts) > 1 else ""
                
                if command in ['quit', 'exit', 'q']:
                    break
                
                elif command == 'help':
                    show_help()
                    continue
                
                elif command == 'settings':
                    show_settings(session)
                    continue
                
                elif command == 'stats':
                    show_stats(session)
                    continue
                
                elif command == 'history':
                    session.display_conversation()
                    continue
                
                elif command == 'clear':
                    if Confirm.ask("Clear conversation history?"):
                        # Keep system prompt but clear rest
                        system_msg = session.conversation_history[0]
                        session.conversation_history = [system_msg]
                        console.print("[green]Conversation history cleared[/green]")
                    continue
                
                elif command == 'temp':
                    try:
                        temp_value = float(args_str)
                        session.update_settings("temperature", temp_value)
                    except ValueError:
                        console.print("[red]Invalid temperature value[/red]")
                    continue
                
                elif command == 'tokens':
                    try:
                        token_value = int(args_str)
                        session.update_settings("max_tokens", token_value)
                    except ValueError:
                        console.print("[red]Invalid token count[/red]")
                    continue
                
                elif command == 'save':
                    filename = args_str.strip() or f"chat_session_{int(time.time())}.json"
                    save_path = Path(filename)
                    session.save_conversation(save_path)
                    console.print(f"[green]Conversation saved to {save_path}[/green]")
                    continue
                
                else:
                    console.print(f"[red]Unknown command: {command}[/red]")
                    console.print("[dim]Type /help for available commands[/dim]")
                    continue
            
            # Generate response
            with console.status("[blue]Thinking..."):
                result = session.generate_response(user_input)
            
            if result["success"]:
                console.print(f"\n[green]Assistant:[/green] {result['response']}")
                
                # Show metadata if verbose
                metadata = result["metadata"]
                console.print(
                    f"[dim]({metadata['tokens_generated']} tokens, "
                    f"{metadata['tokens_per_second']:.1f} tok/s)[/dim]"
                )
            else:
                console.print(f"\n[red]Error: {result['error']}[/red]")
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Chat interrupted[/yellow]")
    
    # Auto-save conversation if requested
    if args.save_conversation:
        session.save_conversation(args.save_conversation)
        console.print(f"[green]Conversation auto-saved to {args.save_conversation}[/green]")
    
    console.print("[blue]Chat session ended. Goodbye![/blue]")
    return 0

if __name__ == "__main__":
    exit(main())
