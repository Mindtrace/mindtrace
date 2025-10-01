#!/usr/bin/env python3
"""Example demonstrating how to use the cm.discord_execute() command.

This script shows how to execute Discord slash commands programmatically through
the FastAPI endpoint. This is useful for exposing AI models and other functionality
through both Discord and HTTP interfaces, ensuring the same logic and loaded models
are used regardless of the request source.

Use cases:
- AI models that can be called via Discord commands or HTTP API
- Shared business logic between Discord and web interfaces
- Testing Discord commands programmatically
- Building web UIs that use the same functionality as Discord bots
"""

import asyncio
import argparse
from mindtrace.services.samples.discord.custom_bot_service import CustomDiscordService
from mindtrace.services.discord.types import DiscordCommandInput


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Demonstrate Discord service execute command usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings
  python discord_execute_example.py
  
  # Run on specific port
  python discord_execute_example.py --port 8080
  
  # Run with custom token
  python discord_execute_example.py --token "your_token_here"
        """
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to run the service on (default: 8080)"
    )
    
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Discord bot token (overrides config)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind the service to (default: localhost)"
    )
    
    return parser.parse_args()


def main():
    """Demonstrate different ways to use cm.discord_execute()."""
    
    args = parse_arguments()
    
    # Launch the Discord service
    print("Launching Discord service...")
    try:
        with CustomDiscordService.launch(
            host=args.host,
            port=args.port,
            token=args.token,
            wait_for_launch=True,
            timeout=30
        ) as cm:
            print("\nTesting discord_execute command:")
            print("=" * 50)
            
            # Method 1: Execute with minimal parameters (only content required)
            print("\n1. Executing /roll with minimal parameters (only content required):")
            result1 = cm.discord_execute(
                content="/roll 20"
            )
            print(f"   Result: {result1.response}")
            
            # Method 2: Execute /help command with no parameters
            print("\n2. Executing /help command with no parameters:")
            result2 = cm.discord_execute(
                content="/help"
            )
            print(f"   Result: {result2.response}")
            
            # Method 3: Execute /service command with minimal parameters
            print("\n3. Executing /service command with minimal parameters:")
            result3 = cm.discord_execute(
                content="/service"
            )
            print(f"   Result: {result3.response}")
            
            # Method 4: Try invalid command (error handling)
            print("\n4. Trying invalid command (error handling):")
            result4 = cm.discord_execute(
                content="/nonexistent"
            )
            print(f"   Result: {result4.response}")
            
            # Method 5: Execute with some optional parameters
            print("\n5. Executing /roll with some optional parameters:")
            result5 = cm.discord_execute(
                content="/roll 6",
                author_id=12345,
                channel_id=67890
            )
            print(f"   Result: {result5.response}")
            
            # Method 6: Execute with all parameters (for commands that need them)
            print("\n6. Executing with all parameters (for guild-specific commands):")
            result6 = cm.discord_execute(
                content="/info",
                author_id=12345,
                channel_id=67890,
                guild_id=11111,
                message_id=22222
            )
            print(f"   Result: {result6.response}")
            
            # Show other available methods
            print("\n7. Other available Discord methods:")
            print("   - cm.discord_status() - Get bot status")
            print("   - cm.discord_commands() - Get list of commands")
            
            # Test status method (with error handling for inf values)
            print("\nBot status:")
            try:
                status = cm.discord_status()
                print(f"   Bot: {status.bot_name}")
                print(f"   Status: {status.status}")
                print(f"   Guilds: {status.guild_count}")
                print(f"   Users: {status.user_count}")
                print(f"   Latency: {status.latency}ms")
            except Exception as e:
                print(f"   Status error: {e}")
            
            # Test commands method
            print("\nAvailable commands:")
            try:
                commands = cm.discord_commands()
                for cmd in commands.commands:
                    print(f"   - {cmd['name']}: {cmd['description']}")
            except Exception as e:
                print(f"   Commands error: {e}")
            
            # Show service information
            print(f"\nService running at: {cm.url}")
            print("   Demonstration complete!")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("Done!")


if __name__ == "__main__":
    main()
