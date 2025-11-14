"""
Vosk-based ASR implementation for Raspberry Pi Zero 2 W and better.
API-compatible replacement for Kaldi ASR.
"""

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from vosk import KaldiRecognizer, Model  # type: ignore

    HAS_VOSK_DEPENDENCIES = True
except ImportError:
    HAS_VOSK_DEPENDENCIES = False
    Model = None  # type: ignore
    KaldiRecognizer = None  # type: ignore


class VoskASR:
    """
    Class handling automatic speech recognition using Vosk.
    API-compatible with the Kaldi ASR class.
    """

    MODELS = {
        "fr_FR": "/opt/vosk/models/vosk-model-small-fr-0.22",
        "en_GB": "/opt/vosk/models/vosk-model-small-en-us-0.15",
        "en_US": "/opt/vosk/models/vosk-model-small-en-us-0.15",
    }
    DEFAULT_LOCALE = "fr_FR"

    @staticmethod
    def get_locale(locale):
        if locale in VoskASR.MODELS:
            return locale
        else:
            return VoskASR.DEFAULT_LOCALE

    def __init__(self, locale):
        if not HAS_VOSK_DEPENDENCIES:
            raise ImportError(
                "Vosk ASR dependencies are not installed. "
                "Install with: pip install -e .[asr-vosk]"
            )
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.recognizer = None
        self._load_model(locale)

    def _load_model(self, locale):
        """Load Vosk model for the specified locale."""
        try:
            locale = VoskASR.get_locale(locale)
            model_path = VoskASR.MODELS[locale]

            if not Path(model_path).exists():
                raise FileNotFoundError(
                    f"Vosk model not found at {model_path}. "
                    f"Please run installation script to download models."
                )

            self.model = Model(model_path)
            # Sample rate is always 16000 Hz for Nabaztag
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)

        except Exception:
            print(traceback.format_exc())
            raise

    def decode_chunk(self, samples, finalize):
        """
        Decode audio chunk asynchronously.

        Args:
            samples: Raw audio bytes (16-bit signed PCM)
            finalize: True if this is the last chunk
        """
        self.executor.submit(lambda s=samples, f=finalize: self._decode_chunk(s, f))

    def _decode_chunk(self, frames, finalize):
        """Internal method to process audio chunk."""
        try:
            if self.recognizer is None:
                return

            if finalize:
                # Final chunk - process and get result
                self.recognizer.AcceptWaveform(frames)
                self.recognizer.FinalResult()
            else:
                # Intermediate chunk - just feed to recognizer
                self.recognizer.AcceptWaveform(frames)

        except Exception:
            print(traceback.format_exc())

    async def get_decoded_string(self, sync):
        """
        Get the decoded transcription string.

        Args:
            sync: If True, blocks until result is available

        Returns:
            Transcribed text string
        """
        if sync:
            future = self.executor.submit(lambda: self._get_decoded_string())
            return future.result()
        else:
            return self._get_decoded_string()

    def _get_decoded_string(self):
        """Extract text from Vosk result JSON."""
        try:
            if self.recognizer is None:
                return ""

            # Get final result from Vosk
            result_json = self.recognizer.FinalResult()
            result = json.loads(result_json)

            # Extract text from result
            text = result.get("text", "")

            # Reset recognizer for next recognition
            # Recreate recognizer to clear state
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)

            return text

        except Exception:
            print(traceback.format_exc())
            return ""
