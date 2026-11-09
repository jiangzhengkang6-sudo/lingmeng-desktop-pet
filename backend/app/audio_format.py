from __future__ import annotations

import struct


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
WAV_HEADER_SIZE = 44


def is_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def looks_like_webm(data: bytes) -> bool:
    return data.startswith(b"\x1a\x45\xdf\xa3")


def pcm_s16le_to_wav(
    pcm: bytes,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> bytes:
    if sample_rate <= 0 or channels <= 0:
        raise ValueError("WAV 音频参数无效")

    block_align = channels * SAMPLE_WIDTH_BYTES
    byte_rate = sample_rate * block_align
    data_size = len(pcm)
    return b"".join((
        b"RIFF",
        struct.pack("<I", 36 + data_size),
        b"WAVE",
        b"fmt ",
        struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, 16),
        b"data",
        struct.pack("<I", data_size),
        pcm,
    ))
