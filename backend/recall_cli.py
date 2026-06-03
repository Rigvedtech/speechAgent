#!/usr/bin/env python3
"""
CLI Tool for Recall.ai Bot Management
Easily create, monitor, and manage meeting bots from command line.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from recall_bot_service import RecallBotService, BotConfig


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def cmd_create(args):
    """Create a new bot."""
    service = RecallBotService()
    
    config = BotConfig(
        meeting_url=args.meeting_url,
        bot_name=args.name,
        websocket_url=args.websocket_url
    )
    
    try:
        bot = service.create_bot(config)
        print(f"✅ Bot created successfully!")
        print(f"Bot ID: {bot['id']}")
        print(f"Status: {bot['status']}")
        print(f"Meeting URL: {args.meeting_url}")
        print(f"\n💡 Bot will join the meeting in ~10 seconds")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_status(args):
    """Check bot status."""
    service = RecallBotService()
    
    try:
        status = service.get_bot_status(args.bot_id)
        print(f"Bot ID: {status['id']}")
        print(f"Status: {status['status']}")
        print(f"Meeting URL: {status.get('meeting_url', 'N/A')}")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_delete(args):
    """Delete a bot."""
    service = RecallBotService()
    
    try:
        success = service.delete_bot(args.bot_id)
        if success:
            print(f"✅ Bot {args.bot_id} deleted successfully")
            return 0
        else:
            print(f"❌ Failed to delete bot {args.bot_id}")
            return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_speak(args):
    """Make bot speak text in meeting."""
    service = RecallBotService()
    from audio_sender import AudioSender
    
    try:
        sender = AudioSender(service)
        success = sender.send_text_to_bot_sync(args.bot_id, args.text)
        
        if success:
            print(f"✅ Audio sent to bot {args.bot_id}")
            return 0
        else:
            print(f"❌ Failed to send audio")
            return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Recall.ai Meeting Bot CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a bot
  %(prog)s create https://teams.microsoft.com/... --websocket-url wss://abc.ngrok.io
  
  # Check bot status
  %(prog)s status <bot-id>
  
  # Make bot speak
  %(prog)s speak <bot-id> "Hello, everyone!"
  
  # Delete bot
  %(prog)s delete <bot-id>
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new bot')
    create_parser.add_argument('meeting_url', help='Meeting URL (Teams/Zoom/Meet)')
    create_parser.add_argument('--name', default='AI Interviewer', help='Bot name')
    create_parser.add_argument('--websocket-url', help='WebSocket URL for audio')
    create_parser.set_defaults(func=cmd_create)
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check bot status')
    status_parser.add_argument('bot_id', help='Bot ID')
    status_parser.set_defaults(func=cmd_status)
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a bot')
    delete_parser.add_argument('bot_id', help='Bot ID')
    delete_parser.set_defaults(func=cmd_delete)
    
    # Speak command
    speak_parser = subparsers.add_parser('speak', help='Make bot speak')
    speak_parser.add_argument('bot_id', help='Bot ID')
    speak_parser.add_argument('text', help='Text to speak')
    speak_parser.set_defaults(func=cmd_speak)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    setup_logging(args.verbose)
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
