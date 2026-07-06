import threading
import sounddevice as sd

from config import STARTUP_GREETING
from state import AgentState
from stt_engine import STTEngine
from llm_brain import LLMBrain
from tts_voice import TTSVoice

def main():
    print("Welcome to SpeechAgent Modular S2S Pipeline!")
    print("[Mode] Standalone interactive mode: startup greeting + local two-way conversation")
    
    # 1. Initialize Shared Global State
    state = AgentState()
    
    # STANDALONE MODE: Auto-start interview (no manual /api/start needed)
    state.is_started.set()  # Allows STT to process audio immediately
    
    # 2. Instantiate all core components
    stt_engine = STTEngine(state)
    llm_brain = LLMBrain(state)
    tts_voice = TTSVoice(state)
    
    # 3. Start TTS first (we'll greet before listening)
    threading.Thread(target=tts_voice.start, daemon=True).start()

    print("\n✅ INFO: If NOT using headphones, your microphone might hear the speakers and interrupt itself!")

    # 4. Device Discovery & Selection
    devices = sd.query_devices()
    BLACKLIST = ['microsoft sound mapper', 'primary sound', 'mapper']
    preferred_indices = []   
    other_indices = []       

    print("\n📋 All input devices found:")
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            name_lower = d['name'].lower()
            is_blacklisted = any(b in name_lower for b in BLACKLIST)
            status = "  [SKIP - virtual]" if is_blacklisted else ""
            print(f"  [{i}] {d['name']} ({int(d['default_samplerate'])}Hz){status}")
            
            if is_blacklisted:
                continue
            if any(kw in name_lower for kw in ['mic', 'head', 'array']):
                preferred_indices.append(i)
            elif 'speaker' not in name_lower and 'mix' not in name_lower:
                other_indices.append(i)

    working_device = None
    for i in preferred_indices + other_indices:
        d = devices[i]
        try:
            native_sr = int(d['default_samplerate'])
            native_ch = min(d['max_input_channels'], 2)
            with sd.InputStream(
                device=i,
                samplerate=native_sr,
                channels=native_ch,
                callback=stt_engine.audio_callback
            ):
                pass 

            working_device = i
            stt_engine.actual_samplerate = native_sr
            stt_engine.actual_channels = native_ch
            print(f"\n✅ Using Microphone: [{i}] {d['name']} ({native_sr}Hz, {native_ch}ch)")
            break
        except Exception as ex:
            print(f"  ⚠️  Device [{i}] {d['name']} failed: {ex}")
            continue

    if working_device is None:
        print("❌ No working microphone found. Please check your audio devices.")
        state.is_running = False
        return

    # First spoken turn: introduction via TTS (matches Prabhat voice persona).
    state.is_ai_speaking.set()
    print(f"[AI]: {STARTUP_GREETING}")
    state.tts_turn_done_event.clear()
    state.tts_queue.put(STARTUP_GREETING)
    state.tts_queue.put("<END_OF_TURN>")

    # Wait until the greeting finishes playback before starting to listen.
    # (No STT thread / mic stream yet, so user can't interrupt the greeting.)
    state.tts_turn_done_event.wait(timeout=60)

    # 4. Start LLM + STT workers after greeting
    threading.Thread(target=llm_brain.start, daemon=True).start()
    threading.Thread(target=stt_engine.process_audio, daemon=True).start()

    # 5. Start Master Audio Stream Loop
    try:
        with sd.InputStream(
            device=working_device,
            samplerate=stt_engine.actual_samplerate,
            channels=stt_engine.actual_channels,
            callback=stt_engine.audio_callback,
            blocksize=int(stt_engine.actual_samplerate * 0.1) # 100ms chunks
        ):
            print("Press Ctrl+C to stop.")
            while state.is_running:
                sd.sleep(100)
    except KeyboardInterrupt:
        print("\nStopping...")
        state.is_running = False
    except Exception as e:
        print(f"\nMicrophone Error: {e}")
        state.is_running = False

if __name__ == "__main__":
    main()
