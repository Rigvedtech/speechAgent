# 🎙️ SpeechAgent Workflow & Technologies

## 📐 System Architecture

```mermaid
graph TD
    subgraph "Phase 1: Audio Capture"
        A[User Speaks] --> B(SoundDevice Library)
        B --> C{Silero VAD - local}
        C -- "Silence" --> B
        C -- "Human Voice" --> D[Audio Buffer]
    end

    subgraph "Phase 2: Speech-to-Text (STT)"
        D --> E(Faster-Whisper - local)
        E --> F[Raw Text]
        F --> G{Regex Filter}
        G -- "Strip 'um/uh'" --> H[Clean Text]
    end

    subgraph "Phase 3: The Brain (LLM)"
        H --> I(Groq LPU - Cloud)
        I -- "Streaming Word-by-Word" --> J[Response Parser]
    end

    subgraph "Phase 4: Text-to-Speech (TTS)"
        J -- "Sentence 1" --> K(Edge-TTS - Cloud)
        J -- "Sentence 2" --> L(Edge-TTS - Cloud)
        K --> M[Pygame Player]
        L --> M
    end

    M --> N[Speakers - AI Voice]
    
    subgraph "Special Feature: Barge-In"
        A -.-> |VAD Interrupt| M
        M -.-> |Stop Audio| N
    end
```

---

## 🛠 Technology & Library Stack

| Component | Technology / Library | Description |
|---|---|---|
| **Audio Capture** | `sounddevice` | Handles real-time microphone streaming. |
| **VAD Filter** | `silero-vad` | Detects human speech patterns and ignores noise. |
| **STT Engine** | `faster-whisper` | Local neural engine for high-accuracy transcription. |
| **LLM Backend** | `groq` | Ultra-fast cloud inference (fallback to `ollama`). |
| **TTS Engine** | `edge-tts` | Cloud-based neural voice synthesis (Microsoft). |
| **Audio Output** | `pygame-ce` | Handles low-latency playback & interruptions. |
| **Data Handler** | `numpy` / `scipy` | Manages audio signal normalization and resampling. |
| **Environment** | `python-dotenv` | Securely manages API keys from a `.env` file. |
