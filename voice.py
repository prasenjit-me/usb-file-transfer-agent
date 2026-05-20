import os
import wave
import tempfile
import threading
import numpy as np
import sounddevice as sd
from openai import OpenAI

SAMPLE_RATE = 16000  # Whisper works best at 16 kHz
CHANNELS = 1


class VoiceRecorder:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self._recording = False
        self._frames: list = []
        self._stream = None

    def start(self):
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time, status):
        if self._recording:
            self._frames.append(indata.copy())

    def stop_and_transcribe(self) -> str:
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            return ""

        audio = np.concatenate(self._frames, axis=0)

        tmp_path = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)          # int16 = 2 bytes per sample
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())

        try:
            with open(tmp_path, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=f,
                    response_format="text",
                )
            return str(result).strip()
        finally:
            os.unlink(tmp_path)
