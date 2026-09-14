"""Testable microphone and shortcut state. No typing content is collected."""
from array import array
from collections import deque
import math
import wave

class ChordGate:
    """Toggle once after releasing a complete chord. Other keys invalidate it."""
    def __init__(self):
        self.armed = False
        self.blocked = False
        self.since = 0.0

    def update(self, both, either, other, now):
        if both and not self.armed:
            self.armed = True
            self.since = now
            self.blocked = bool(other)
        if self.armed and other:
            self.blocked = True
        if self.armed and not either:
            trigger = not self.blocked and .04 <= now - self.since <= 2.0
            self.armed = self.blocked = False
            return trigger
        return False


def amplitude(raw):
    samples = array('h', raw)
    if not samples:
        return 0.0
    rms = math.sqrt(sum(v*v for v in samples) / len(samples)) / 32768
    return max(0.0, min(1.0, rms * 9))


class Recorder:
    def __init__(self, audio):
        self.audio = audio
        self.stream = None
        self.chunks = []
        self.latest = b''
        self.rate = 16000
        self.frames = 0
        self.warning = ''
        self.keep_audio = True
        self.done = False

    def start(self, device=None, keep_audio=True):
        self.close()
        self.chunks, self.latest = [], b''
        self.frames, self.warning, self.done = 0, '', False
        self.keep_audio = keep_audio
        info = self.audio.query_devices(device, 'input')
        preferred = int(info['default_samplerate'])
        # Use the device's native sample rate; Groq accepts WAV and resamples.
        self.rate = preferred if preferred > 0 else 16000
        self.audio.check_input_settings(device=device, channels=1, dtype='int16', samplerate=self.rate)
        self.stream = self.audio.RawInputStream(device=device, channels=1, dtype='int16', samplerate=self.rate, blocksize=0, callback=self.callback)
        try:
            self.stream.start()
        except Exception:
            self.close()
            raise

    def callback(self, data, frames, timing, status):
        if status:
            self.warning = str(status)
        if self.frames >= self.rate * 120:
            self.done = True
            return
        block = bytes(data)
        self.latest = block
        if self.keep_audio:
            self.chunks.append(block)
        self.frames += frames

    @property
    def level(self):
        return amplitude(self.latest[-4096:])

    def save(self, path):
        self.close()
        with wave.open(str(path), 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(self.rate)
            f.writeframes(b''.join(self.chunks))
        self.chunks.clear()

    def close(self):
        stream, self.stream = self.stream, None
        if stream:
            try:
                stream.stop()
            finally:
                stream.close()

    def discard(self):
        self.close()
        self.chunks.clear()
        self.latest = b''
