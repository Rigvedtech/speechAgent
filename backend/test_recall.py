"""
Quick Test Script for Recall.ai Integration
Tests bot creation and basic functionality.
"""

import os
import sys
import time
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import services
from recall_bot_service import RecallBotService, BotConfig


def test_bot_creation():
    """Test creating a bot."""
    print("\n" + "="*60)
    print("Testing Recall.ai Bot Creation")
    print("="*60 + "\n")
    
    # Check environment
    api_key = os.getenv("RECALL_API_KEY")
    if not api_key:
        print("❌ ERROR: RECALL_API_KEY not found in .env")
        print("Please add your Recall.ai API key to .env file")
        return False
    
    websocket_url = os.getenv("PUBLIC_WEBSOCKET_URL")
    if not websocket_url:
        print("⚠️  WARNING: PUBLIC_WEBSOCKET_URL not set")
        print("Bot will be created but won't stream audio to your server")
    
    # Get meeting URL from user
    print("Enter a meeting URL (Teams/Zoom/Google Meet):")
    print("Example: https://teams.microsoft.com/l/meetup-join/...")
    meeting_url = input("> ").strip()
    
    if not meeting_url:
        print("❌ No meeting URL provided")
        return False
    
    # Create service
    try:
        service = RecallBotService(api_key)
        print("✅ Recall.ai service initialized")
    except Exception as e:
        print(f"❌ Failed to initialize service: {e}")
        return False
    
    # Create bot
    print(f"\n📞 Creating bot for meeting: {meeting_url}")
    
    config = BotConfig(
        meeting_url=meeting_url,
        bot_name="Test Bot",
        websocket_url=websocket_url
    )
    
    try:
        bot = service.create_bot(config)
        bot_id = bot['id']
        
        print("\n✅ Bot created successfully!")
        print(f"Bot ID: {bot_id}")
        print(f"Status: {bot['status']}")
        
        # Monitor status
        print("\n⏳ Waiting for bot to join (10 seconds)...")
        time.sleep(10)
        
        status = service.get_bot_status(bot_id)
        print(f"Current status: {status['status']}")
        
        if status['status'] == 'in_call':
            print("✅ Bot successfully joined the meeting!")
        elif status['status'] == 'in_waiting_room':
            print("⏳ Bot is in waiting room (organizer must admit)")
        else:
            print(f"ℹ️  Bot status: {status['status']}")
        
        # Ask if user wants to delete bot
        print("\n" + "-"*60)
        delete = input("Delete bot? (y/n): ").strip().lower()
        
        if delete == 'y':
            if service.delete_bot(bot_id):
                print("✅ Bot deleted successfully")
            else:
                print("❌ Failed to delete bot")
        else:
            print(f"ℹ️  Bot {bot_id} is still in the meeting")
            print("You can delete it later using:")
            print(f"  python recall_cli.py delete {bot_id}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_environment():
    """Check if environment is properly configured."""
    print("\n" + "="*60)
    print("Environment Check")
    print("="*60 + "\n")
    
    checks = {
        "RECALL_API_KEY": os.getenv("RECALL_API_KEY"),
        "PUBLIC_WEBSOCKET_URL": os.getenv("PUBLIC_WEBSOCKET_URL"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
    }
    
    all_good = True
    
    for key, value in checks.items():
        status = "✅" if value else "❌"
        required = "REQUIRED" if key in ["RECALL_API_KEY"] else "optional"
        print(f"{status} {key}: {'Set' if value else f'Not set ({required})'}")
        
        if not value and key == "RECALL_API_KEY":
            all_good = False
    
    print()
    
    if not all_good:
        print("❌ Please set required environment variables in .env file")
        print("Copy .env.example to .env and fill in your keys")
        return False
    
    return True


def main():
    """Main test runner."""
    print("\n🤖 Recall.ai Integration Test Suite\n")
    
    # Check environment
    if not check_environment():
        return 1
    
    # Ask what to test
    print("\nWhat would you like to test?")
    print("1. Create a test bot")
    print("2. Exit")
    
    choice = input("\nChoice (1-2): ").strip()
    
    if choice == "1":
        test_bot_creation()
    else:
        print("Exiting...")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
