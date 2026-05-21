import os
import time
import wave
import queue
import tempfile
import threading
import numpy as np
import sounddevice as sd
import pyttsx3
from openai import OpenAI

SAMPLE_RATE       = 16000
CHANNELS          = 1
CHUNK_MS          = 80
CHUNK_SAMPLES     = int(SAMPLE_RATE * CHUNK_MS / 1000)
SPEECH_THRESH     = 350
SILENCE_SECS      = 1.5
SILENCE_CHUNKS    = int(SILENCE_SECS * 1000 / CHUNK_MS)
MIN_SPEECH_CHUNKS = 4                               # ignore sounds < ~320 ms
COOLDOWN_CHUNKS   = int(0.6 * 1000 / CHUNK_MS)     # 0.6 s deaf after TTS ends


class VoiceAgent:
    """
    Fully hands-free voice loop:
      VAD → Whisper STT → on_transcript() → caller does AI → speak() → back to VAD
    """

    def __init__(self, api_key: str, on_state, on_transcript):
        self.client        = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.on_state      = on_state
        self.on_transcript = on_transcript
        self._running      = False
        self._busy         = False   # True while transcribing / waiting for AI / speaking

        # ── Dedicated TTS thread ─────────────────────────────────────────────
        # pyttsx3 (Windows SAPI5) must be initialised AND called on the SAME
        # thread.  A queue lets background callers submit text safely.
        self._tts_q = queue.Queue()
        threading.Thread(target=self._tts_worker, daemon=True).start()

    # ── TTS worker (owns the pyttsx3 engine) ────────────────────────────────

    def _tts_worker(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 0.9)
        while True:
            item = self._tts_q.get()
            if item is None:          # shutdown signal
                break
            text, done_evt = item
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass
            finally:
                done_evt.set()        # unblock speak()

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._busy    = False
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self._tts_q.put(None)         # tell TTS worker to exit

    def speak(self, text: str):
        """
        Queue text for TTS and block until spoken.
        Call from any background thread — safe because TTS runs on its own thread.
        After speaking, releases _busy and resumes listening.
        """
        self.on_state("speaking")
        done = threading.Event()
        self._tts_q.put((text, done))
        done.wait()                   # block caller until TTS finishes
        self._busy = False
        if self._running:
            self.on_state("listening")

    def resume(self):
        """Release busy flag when the AI call fails (so speak() is never called)."""
        self._busy = False
        if self._running:
            self.on_state("listening")

    # ── VAD listen loop ──────────────────────────────────────────────────────

    def _listen_loop(self):
        frames: list  = []
        silence_count = 0
        speech_count  = 0
        capturing     = False
        cooldown      = 0

        self.on_state("listening")

        # Always read from stream — never sleep-and-pause — so the mic buffer
        # never overflows with stale audio when we resume after TTS.
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
            while self._running:
                chunk, _ = stream.read(CHUNK_SAMPLES)

                # ── Drain buffer silently while busy or in cooldown ──────────
                if self._busy:
                    cooldown = COOLDOWN_CHUNKS   # reset cooldown every busy tick
                    capturing = False
                    frames = []
                    continue

                if cooldown > 0:
                    cooldown -= 1
                    continue

                # ── Voice Activity Detection ─────────────────────────────────
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

                if rms > SPEECH_THRESH:
                    if not capturing:
                        capturing    = True
                        frames       = []
                        speech_count = 0
                        self.on_state("hearing")
                    silence_count = 0
                    speech_count += 1
                    frames.append(chunk.copy())

                elif capturing:
                    frames.append(chunk.copy())
                    silence_count += 1

                    if silence_count >= SILENCE_CHUNKS:
                        capturing     = False
                        silence_count = 0

                        if speech_count >= MIN_SPEECH_CHUNKS:
                            self._busy = True
                            self.on_state("processing")
                            audio = np.concatenate(frames, axis=0)
                            threading.Thread(
                                target=self._process, args=(audio,), daemon=True
                            ).start()
                        else:
                            self.on_state("listening")   # too short — ignore

                        frames       = []
                        speech_count = 0

        self.on_state("off")

    # ── STT ──────────────────────────────────────────────────────────────────

    def _process(self, audio: np.ndarray):
        text = self._transcribe(audio)
        if text:
            self.on_transcript(text)   # _busy stays True; caller must call speak() or resume()
        else:
            self._busy = False
            if self._running:
                self.on_state("listening")

    def _transcribe(self, audio: np.ndarray) -> str:
        tmp = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        try:
            with open(tmp, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=f,
                    response_format="text",
                )
            return str(result).strip()
        except Exception:
            return ""
        finally:
            os.unlink(tmp)
