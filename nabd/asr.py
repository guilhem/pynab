import struct
import traceback
from concurrent.futures import ThreadPoolExecutor

# Try to import Kaldi ASR dependencies
try:
    import numpy as np
    from kaldiasr.nnet3 import (  # type: ignore
        KaldiNNet3OnlineDecoder,
        KaldiNNet3OnlineModel,
    )

    HAS_KALDI_DEPENDENCIES = True
except ImportError:
    HAS_KALDI_DEPENDENCIES = False
    np = None  # type: ignore
    KaldiNNet3OnlineDecoder = None  # type: ignore
    KaldiNNet3OnlineModel = None  # type: ignore

# Try to import Vosk ASR
try:
    from .asr_vosk import HAS_VOSK_DEPENDENCIES, VoskASR
except ImportError:
    VoskASR = None  # type: ignore
    HAS_VOSK_DEPENDENCIES = False

# Try to detect hardware
try:
    from nabcommon.hardware_detect import can_use_vosk
except ImportError:
    can_use_vosk = lambda: False  # type: ignore


def create_asr(locale):
    """
    Factory function to create appropriate ASR instance based on hardware.

    Returns VoskASR for Pi Zero 2 W and better hardware.
    Returns KaldiASR for Pi Zero W or if Vosk is not available.
    """
    # Check if we can and should use Vosk
    if HAS_VOSK_DEPENDENCIES and can_use_vosk():
        try:
            return VoskASR(locale)
        except Exception as e:
            print(f"Failed to initialize Vosk ASR, falling back to Kaldi: {e}")
            if HAS_KALDI_DEPENDENCIES:
                return KaldiASR(locale)
            raise

    # Fall back to Kaldi
    if HAS_KALDI_DEPENDENCIES:
        return KaldiASR(locale)

    # No ASR available
    raise ImportError(
        "No ASR dependencies available. "
        "Install with: pip install -e .[asr-kaldi] or pip install -e .[asr-vosk]"
    )


# Keep ASR as an alias to KaldiASR for backward compatibility
# But prefer using create_asr() factory function
class KaldiASR:
    """
    Class handling automatic speech recognition using Kaldi.
    Legacy implementation for Pi Zero W and fallback.
    """

    MODELS = {
        "fr_FR": "/opt/kaldi/model/kaldi-nabaztag-fr-adapt-r20200203",
        "en_GB": "/opt/kaldi/model/kaldi-nabaztag-en-adapt-r20191222",
        "en_US": "/opt/kaldi/model/kaldi-nabaztag-en-adapt-r20191222",
    }
    DEFAULT_LOCALE = "fr_FR"

    @staticmethod
    def get_locale(locale):
        if locale in KaldiASR.MODELS:
            return locale
        else:
            return KaldiASR.DEFAULT_LOCALE

    def __init__(self, locale):
        if not HAS_KALDI_DEPENDENCIES:
            raise ImportError(
                "Kaldi ASR dependencies (numpy, py-kaldi-asr) are not installed. "
                "Install with: pip install -e .[asr-kaldi]"
            )
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._load_model(locale)

    def _load_model(self, locale):
        locale = KaldiASR.get_locale(locale)
        path = KaldiASR.MODELS[locale]
        self.model = KaldiNNet3OnlineModel(path, max_mem=20000)
        self.decoder = KaldiNNet3OnlineDecoder(self.model)

    def decode_chunk(self, samples, finalize):
        self.executor.submit(lambda s=samples, f=finalize: self._decode_chunk(s, f))

    def _decode_chunk(self, frames, finalize):
        try:
            nframes = len(frames) / 2
            samples = struct.unpack_from("<%dh" % nframes, frames)
            self.decoder.decode(16000, np.array(samples, dtype=np.float32), finalize)
        except Exception:
            print(traceback.format_exc())

    async def get_decoded_string(self, sync):
        if sync:
            future = self.executor.submit(lambda: self._get_decoded_string())
            return future.result()
        else:
            # not sure we could do that
            text, likelihood = self.decoder.get_decoded_string()
            return text

    def _get_decoded_string(self):
        try:
            text, likelihood = self.decoder.get_decoded_string()
            return text
        except Exception:
            print(traceback.format_exc())


# Backward compatibility alias
ASR = KaldiASR
