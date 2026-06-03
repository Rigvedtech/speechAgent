# Recall.ai Meeting Bot Integration

## 🎯 Overview

This integration allows your AI interviewer bot to join **Teams, Zoom, and Google Meet** meetings using [Recall.ai](https://recall.ai). The bot captures audio, processes it through your existing STT/LLM/TTS pipeline, and responds in real-time.

## 🏗️ Architecture

```
Meeting (Teams/Zoom/Meet)
    │
    ↓
Recall.ai Bot (Cloud) ← Creates & manages bot
    │
    ├─ Audio Stream ──→ WebSocket ──→ Your Server
    │                                      │
    │                                      ↓
    │                                 STT Engine
    │                                      │
    │                                      ↓
    │                                  LLM Brain
    │                                      │
    │                                      ↓
    │                                  TTS Engine
    │                                      │
    ↓                                      ↓
Bot speaks ←─── Output Audio API ←─── Audio File
```

## 📋 Prerequisites

1. **Recall.ai Account**
   - Sign up at [recall.ai](https://recall.ai)
   - Get your API key (5 free hours included)

2. **ngrok** (for development)
   ```bash
   # Download from https://ngrok.com
   # Or install via:
   choco install ngrok     # Windows
   brew install ngrok      # Mac
   ```

3. **Python 3.8+**

4. **ffmpeg** (optional, for better audio quality)
   ```bash
   choco install ffmpeg    # Windows
   brew install ffmpeg     # Mac
   ```

## 🚀 Quick Start

### Step 1: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your keys:
# - RECALL_API_KEY
# - GROQ_API_KEY (optional, can use Ollama)
```

### Step 3: Start WebSocket Server

```bash
# Terminal 1: Start the bot server
python recall_main.py
```

You should see:
```
============================================================
Recall.ai Meeting Bot Started
============================================================
WebSocket server: ws://0.0.0.0:8765
============================================================
```

### Step 4: Expose with ngrok

```bash
# Terminal 2: Expose WebSocket server
ngrok http 8765
```

Copy the ngrok URL (e.g., `https://abc123.ngrok-free.app`)

### Step 5: Update Environment

```bash
# Add to .env file:
PUBLIC_WEBSOCKET_URL=wss://abc123.ngrok-free.app
```

Restart `recall_main.py` to load new config.

### Step 6: Create Bot & Join Meeting

#### Option A: Python API

```python
from recall_bot_service import RecallBotService, BotConfig

service = RecallBotService()
config = BotConfig(
    meeting_url="https://teams.microsoft.com/l/meetup-join/...",
    bot_name="AI Interviewer",
    websocket_url="wss://abc123.ngrok-free.app"
)

bot = service.create_bot(config)
print(f"Bot ID: {bot['id']}")
```

#### Option B: curl

```bash
curl --request POST \
  --url https://us-west-2.recall.ai/api/v1/bot/ \
  --header "Authorization: Token YOUR_RECALL_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "meeting_url": "YOUR_MEETING_URL",
    "bot_name": "AI Interviewer",
    "recording_config": {
      "audio_mixed_raw": {},
      "realtime_endpoints": [{
        "type": "websocket",
        "url": "wss://YOUR_NGROK_URL",
        "events": ["audio_mixed_raw.data"]
      }]
    }
  }'
```

## 📁 File Structure

```
backend/
├── recall_main.py              # Main entry point
├── recall_bot_service.py       # Bot creation & management
├── audio_receiver.py           # WebSocket server for audio
├── audio_sender.py             # TTS & send audio to bot
├── session_manager.py          # Multi-session management
├── stt_engine.py               # STT (modified for external audio)
├── llm_brain.py                # LLM processing (unchanged)
├── config.py                   # Configuration (unchanged)
├── state.py                    # Shared state (unchanged)
└── requirements.txt            # Dependencies
```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RECALL_API_KEY` | ✅ Yes | - | Your Recall.ai API key |
| `PUBLIC_WEBSOCKET_URL` | ✅ Yes* | - | Public WebSocket URL (ngrok) |
| `WEBSOCKET_HOST` | No | 0.0.0.0 | WebSocket bind address |
| `WEBSOCKET_PORT` | No | 8765 | WebSocket port |
| `GROQ_API_KEY` | No | - | Groq API key (faster LLM) |
| `TTS_VOICE` | No | en-IN-PrabhatNeural | Edge-TTS voice |

*Required for bot creation

## 🎮 Usage Examples

### Example 1: Join Teams Meeting

```python
from recall_main import RecallMeetingBot

app = RecallMeetingBot()

# Join meeting
bot_id = app.create_bot_for_meeting(
    meeting_url="https://teams.microsoft.com/l/meetup-join/...",
    bot_name="AI Interviewer"
)

print(f"Bot joined with ID: {bot_id}")
# Bot will automatically process audio and respond
```

### Example 2: Multiple Concurrent Meetings

```python
# The session manager handles multiple meetings automatically
bot_id_1 = app.create_bot_for_meeting(meeting_url_1)
bot_id_2 = app.create_bot_for_meeting(meeting_url_2)

# Each meeting has its own STT/LLM/TTS pipeline
```

### Example 3: Manual Bot Control

```python
from recall_bot_service import RecallBotService

service = RecallBotService()

# Check bot status
status = service.get_bot_status(bot_id)
print(f"Status: {status['status']}")

# Send audio manually
with open("greeting.wav", "rb") as f:
    audio_data = f.read()
    service.send_audio_to_bot(bot_id, audio_data, "wav")

# End meeting
service.delete_bot(bot_id)
```

## 🐛 Troubleshooting

### Bot Not Joining Meeting

**Check:**
1. Meeting URL is valid and accessible
2. Meeting hasn't ended
3. Recall.ai API key is correct
4. Bot isn't stuck in lobby (organizer must admit)

**Logs:**
```bash
# Check bot status
curl -H "Authorization: Token YOUR_KEY" \
  https://us-west-2.recall.ai/api/v1/bot/BOT_ID/
```

### No Audio Received

**Check:**
1. ngrok is running and WebSocket is exposed
2. `PUBLIC_WEBSOCKET_URL` matches ngrok URL
3. WebSocket server is running (`recall_main.py`)
4. Check logs for connection errors

### Bot Not Speaking

**Check:**
1. ffmpeg is installed (for best quality)
2. TTS queue is receiving text (check logs)
3. Audio is being generated (check `tmp_audio/` folder)
4. Recall.ai API isn't rate-limited

## 📊 Monitoring

### Check Active Sessions

```python
from session_manager import SessionManager

manager = app.session_manager
sessions = manager.get_active_sessions()

for bot_id, session in sessions.items():
    print(f"Bot {bot_id}: Active={session.is_active}")
```

### View Logs

```bash
# Real-time logs
tail -f recall_bot.log

# Filter by level
grep "ERROR" recall_bot.log
```

## 🚀 Production Deployment

### Step 1: Deploy to Cloud

**Option A: AWS EC2**
```bash
# Launch Ubuntu instance (t3.xlarge recommended)
# Install dependencies
sudo apt update
sudo apt install python3-pip ffmpeg
pip3 install -r requirements.txt

# Configure .env
nano .env

# Run with systemd
sudo cp recall-bot.service /etc/systemd/system/
sudo systemctl enable recall-bot
sudo systemctl start recall-bot
```

**Option B: Docker**
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "recall_main.py"]
```

### Step 2: Setup Domain & SSL

```bash
# Get domain (e.g., bot.yourcompany.com)
# Point to your server IP

# Install certbot
sudo apt install certbot

# Get SSL certificate
sudo certbot certonly --standalone -d bot.yourcompany.com

# Update .env
PUBLIC_WEBSOCKET_URL=wss://bot.yourcompany.com
```

### Step 3: Production Settings

```bash
# .env for production
WEBSOCKET_HOST=0.0.0.0
WEBSOCKET_PORT=443  # Use 443 for wss://
PUBLIC_WEBSOCKET_URL=wss://bot.yourcompany.com
```

## 💰 Cost Estimation

**Recall.ai:**
- First 5 hours: FREE
- After: $0.50/hour of recording
- Example: 10 meetings × 30 min = $2.50

**Cloud Hosting:**
- AWS t3.xlarge: ~$120/month
- or DigitalOcean: ~$48/month

**Total:** ~$50-150/month (depending on meeting volume)

## 📚 API Reference

### RecallBotService

```python
service = RecallBotService(api_key="...")

# Create bot
bot = service.create_bot(config)

# Get status
status = service.get_bot_status(bot_id)

# Send audio
service.send_audio_to_bot(bot_id, audio_data, "wav")

# Delete bot
service.delete_bot(bot_id)
```

### SessionManager

```python
manager = SessionManager(recall_service)

# Create session
session = manager.create_session(bot_id, meeting_url)

# Handle audio (called automatically by WebSocket)
manager.handle_audio_chunk(bot_id, audio_array)

# End session
manager.end_session(bot_id)
```

## 🔗 Resources

- [Recall.ai Documentation](https://docs.recall.ai)
- [Recall.ai Pricing](https://www.recall.ai/pricing)
- [ngrok Documentation](https://ngrok.com/docs)

## ❓ FAQ

**Q: Can I use localhost without ngrok?**
A: No, Recall.ai needs a public URL to send audio. Use ngrok for dev or cloud deployment for production.

**Q: Do I need a Teams/Zoom account for the bot?**
A: No! Bot joins using just the meeting URL.

**Q: Can the bot join password-protected meetings?**
A: Only if the meeting URL includes the password or bot is admitted from lobby.

**Q: How many concurrent meetings can I handle?**
A: Depends on your server resources. Each meeting needs ~2GB RAM + CPU for STT/LLM.

## 📝 License

MIT License - See LICENSE file for details.
