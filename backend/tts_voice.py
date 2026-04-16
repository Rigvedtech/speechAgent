import os
import time
import queue
import asyncio
import tempfile
import threading
import sys
import subprocess
import edge_tts
from config import TTS_VOICE, TTS_RATE
from state import AgentState

class TTSVoice:
    def __init__(self, state: AgentState):
        self.state = state
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
        import pygame
        pygame.mixer.init()
        self.pygame = pygame

    def start(self):
        """Two-stage TTS pipeline for zero-gap speech."""
        play_queue = queue.Queue()
        END_SIGNAL = "<PLAY_DONE>"

        def speak_fallback_windows(text: str):
            if sys.platform != "win32":
                return False
            if not text or not text.strip():
                return True

            # Use Windows SAPI (System.Speech) via PowerShell as a last-resort fallback.
            safe = text.replace("`", "``").replace('"', '`"')
            ps = (
                "Add-Type -AssemblyName System.Speech; "
                '$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                f'$speak.Speak("{safe}");'
            )
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                    check=False,
                    timeout=15,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return True
            except Exception:
                return False

        def generate_audio(text, output_file):
            communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
            asyncio.run(communicate.save(output_file))

        def generator_stage():
            while self.state.is_running:
                try:
                    sentence = self.state.tts_queue.get(timeout=1.0)
                    if sentence == "<END_OF_TURN>":
                        play_queue.put(END_SIGNAL)
                        continue

                    if self.state.interrupt_flag:
                        continue

                    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                    temp_file = tmp.name
                    tmp.close()

                    try:
                        # Retry a couple times for transient Edge-TTS failures.
                        last_err = None
                        for _ in range(3):
                            try:
                                generate_audio(sentence, temp_file)
                                last_err = None
                                break
                            except Exception as e:
                                last_err = e
                                time.sleep(0.25)

                        if last_err is not None:
                            raise last_err

                        play_queue.put(temp_file)
                    except Exception as e:
                        print(f"TTS Generation Error: {e}")
                        try:
                            os.unlink(temp_file)
                        except Exception:
                            pass
                        # Spoken fallback so the user doesn't get silence.
                        if not self.state.interrupt_flag:
                            speak_fallback_windows(sentence)

                except queue.Empty:
                    continue

        def player_stage():
            while self.state.is_running:
                try:
                    item = play_queue.get(timeout=1.0)
                    if item == END_SIGNAL:
                        self.state.is_ai_speaking = False
                        # Notify anyone waiting for the end of this spoken turn.
                        try:
                            self.state.tts_turn_done_event.set()
                        except Exception:
                            pass
                        print("--- READY: START SPEAKING ---")
                        continue

                    temp_file = item
                    if self.state.interrupt_flag:
                        try:
                            os.unlink(temp_file)
                        except Exception:
                            pass
                        continue

                    try:
                        self.pygame.mixer.music.load(temp_file)
                        self.pygame.mixer.music.play()

                        while self.pygame.mixer.music.get_busy():
                            if self.state.interrupt_flag:
                                self.pygame.mixer.music.stop()
                                for q in [self.state.tts_queue, play_queue]:
                                    while not q.empty():
                                        try:
                                            leftover = q.get_nowait()
                                            if isinstance(leftover, str) and leftover.endswith(".mp3"):
                                                try:
                                                    os.unlink(leftover)
                                                except Exception:
                                                    pass
                                        except queue.Empty:
                                            break
                                break
                            time.sleep(0.05)
                    finally:
                        self.pygame.mixer.music.unload()
                        try:
                            os.unlink(temp_file)
                        except Exception:
                            pass

                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"TTS Player Error: {e}")

        # Start the generator as a daemon sub-thread
        threading.Thread(target=generator_stage, daemon=True).start()
        # The player runs perfectly as the main loop for this thread
        player_stage()
