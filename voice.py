import os
import time
import wave
import tempfile
import threading
import numpy as np
import sounddevice as sd
import pyttsx3
from openai import OpenAI

SAMPLE_RATE     = 16000
CHANNELS        = 1
CHUNK_MS        = 80                                    # process audio in 80ms chunks
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_MS / 1000)
SPEECH_THRESH   = 350                                   # RMS level considered as speech
SILENCE_SECS    = 1.5                                   # silence after speech → end of utterance
SILENCE_CHUNKS  = int(SILENCE_SECS * 1000 / CHUNK_MS)
MIN_SPEECH_CHUNKS = 4                                   # ignore sounds shorter than ~320ms


class VoiceAgent:
    """
    Hands-free voice loop:
      listen → VAD → Whisper STT → on_transcript() → (caller does AI) → speak() → listen
    """

    def __init__(self, api_key: str, on_state, on_transcript):
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.on_state      = on_state       # callback(state: str) — called from bg thread
        self.on_transcript = on_transcript  # callback(text: str)  — called from bg thread
        self._running = False
        self._busy    = False               # True while processing or speaking

        self._tts = pyttsx3.init()
        self._tts.setProperty("rate", 165)
        self._tts.setProperty("volume", 0.9)

    # ── Lifecycle ───────────────────────────────────

    def start(self):
        self._running = True
        self._busy    = False
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self._running = False

    # ── Called by GUI after AI produces a reply ─────

    def speak(self, text: str):
        """Speak the reply then resume listening. Must be called from a bg thread."""
        self.on_state("speaking")
        try:
            self._tts.say(text)
            self._tts.runAndWait()
        finally:
            self._busy = False
            if self._running:
                self.on_state("listening")

    def resume(self):
        """Call if the AI fails so busy flag is released."""
        self._busy = False
        if self._running:
            self.on_state("listening")

    # ── VAD listen loop ─────────────────────────────

    def _listen_loop(self):
        frames: list = []
        silence_count = 0
        speech_count  = 0
        capturing     = False

        self.on_state("listening")

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
            while self._running:
                if self._busy:
                    time.sleep(0.05)
                    continue

                chunk, _ = stream.read(CHUNK_SAMPLES)
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
                            self.on_state("listening")

                        frames       = []
                        speech_count = 0

        self.on_state("off")

    def _process(self, audio: np.ndarray):
        text = self._transcribe(audio)
        if text:
            self.on_transcript(text)   # GUI takes it from here; _busy stays True
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
