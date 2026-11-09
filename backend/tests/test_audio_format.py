from __future__ import annotations

import struct

from backend.app.audio_format import is_wav, looks_like_webm, pcm_s16le_to_wav


def test_pcm_is_wrapped_as_mono_16khz_wav() -> None:
    pcm = b"\x00\x01" * 10
    wav = pcm_s16le_to_wav(pcm)

    assert is_wav(wav)
    assert wav[:4] == b"RIFF"
    assert struct.unpack("<I", wav[4:8])[0] == 36 + len(pcm)
    assert struct.unpack("<H", wav[22:24])[0] == 1
    assert struct.unpack("<I", wav[24:28])[0] == 16_000
    assert struct.unpack("<H", wav[34:36])[0] == 16
    assert wav[44:] == pcm


def test_detects_wav_and_webm_headers() -> None:
    assert is_wav(b"RIFF" + b"\x00" * 4 + b"WAVE")
    assert looks_like_webm(b"\x1a\x45\xdf\xa3\x00")
    assert not looks_like_webm(b"\x00\x00\x00\x00")
