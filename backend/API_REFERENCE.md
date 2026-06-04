# API Reference - Voice Interview Bot

Base URL: `http://localhost:8000`

---

## 1. Join Meeting

**Endpoint:** `POST /api/join`

**Purpose:** Creates bot and joins Teams/Zoom/Google Meet meeting

**Requirements:**
- `meeting_url` (required) - Full meeting URL
- `bot_name` (optional) - Bot display name (defaults to "Prabhat")

**Request:**
```json
{
  "meeting_url": "https://teams.microsoft.com/...",
  "bot_name": "Prabhat"
}
```

**Response:**
```json
{
  "success": true,
  "bot_id": "abc-123",
  "bot_name": "Prabhat",
  "meeting_url": "...",
  "status": "joining"
}
```

---

## 2. Start Interview

**Endpoint:** `POST /api/start/{bot_id}`

**Purpose:** Triggers bot to greet candidate and start interview

**Requirements:**
- `bot_id` (required) - Bot ID from /api/join
- `greeting_message` (optional) - Custom greeting text

**Request:**
```json
{
  "greeting_message": "Hello, let's begin the interview..."
}
```

**Response:**
```json
{
  "success": true,
  "bot_id": "abc-123",
  "message": "Interview started",
  "greeting": "Hello Pranay, I am Prabhat..."
}
```

---

## 3. Leave Meeting

**Endpoint:** `DELETE /api/leave/{bot_id}`

**Purpose:** Removes bot from meeting and cleans up session

**Requirements:**
- `bot_id` (required) - Bot ID to remove

**Response:**
```json
{
  "success": true,
  "bot_id": "abc-123",
  "message": "Bot removed from meeting"
}
```

---

## 4. Get Bot Status

**Endpoint:** `GET /api/status/{bot_id}`

**Purpose:** Gets current bot status and meeting info

**Requirements:**
- `bot_id` (required) - Bot ID to check

**Response:**
```json
{
  "bot_id": "abc-123",
  "status": "in_call_recording",
  "meeting_url": "...",
  "is_active": true
}
```

---

## 5. List Active Sessions

**Endpoint:** `GET /api/sessions`

**Purpose:** Lists all active bot sessions with start status

**Requirements:** None

**Response:**
```json
{
  "active_sessions": 2,
  "bots": [
    {
      "bot_id": "abc-123",
      "meeting_url": "...",
      "is_active": true,
      "is_started": true
    }
  ]
}
```

---

## 6. List Active Meetings

**Endpoint:** `GET /api/active_meetings`

**Purpose:** Shows which meetings have active bots (prevents duplicates)

**Requirements:** None

**Response:**
```json
{
  "active_meetings": 1,
  "meetings": [
    {
      "meeting_url": "https://teams.microsoft.com/...",
      "bot_id": "abc-123",
      "status": "active"
    }
  ]
}
```

---

## 7. Audio Diagnostics

**Endpoint:** `GET /api/diagnostic/audio`

**Purpose:** Explains bot audio behavior and troubleshooting

**Requirements:** None

**Response:**
```json
{
  "bot_audio_behavior": {
    "why_bot_shows_muted": "...",
    "does_mute_prevent_speaking": false
  },
  "current_bot_status": {...},
  "troubleshooting": {...}
}
```

---

## 8. Health Check

**Endpoint:** `GET /health`

**Purpose:** Server health and configuration check

**Requirements:** None

**Response:**
```json
{
  "status": "healthy",
  "service": "recall-bot-api",
  "websocket_url": "wss://...",
  "bot_name": "Prabhat"
}
```

---

## Typical Workflow

```
1. POST /api/join
   → Bot joins meeting (silent)

2. POST /api/start/{bot_id}
   → Bot greets and starts interview

3. (Interview happens - bot listens and responds)

4. DELETE /api/leave/{bot_id}
   → Bot leaves meeting
```

---

## Error Responses

All endpoints return standard error format:

```json
{
  "detail": "Error message here"
}
```

**Common Status Codes:**
- `200` - Success
- `400` - Bad request (invalid parameters)
- `404` - Bot not found
- `500` - Server error
