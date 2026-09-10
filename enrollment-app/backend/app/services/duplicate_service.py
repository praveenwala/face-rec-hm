"""Duplicate detection helpers (Phase 5, contracts/photo-quality.md).

Two distinct concepts, deliberately separate:

1. **Exact file duplicate** — deterministic SHA-256 of the uploaded bytes, used as
   the photo's ``duplicate_group`` (hard gate: only ONE member of an exact duplicate
   group may count toward readiness; research.md #5 / user's Phase 5 rule #15).

2. **Perceptual near-duplicate** — pHash (DCT-based, 16x16 low-frequency block,
   256-bit) computed from the decoded image. Used ONLY as advisory metadata in the
   MVP: if a photo is within ``DUP_HASH_DISTANCE`` of an existing same-person photo,
   the analysis records an advisory note. It NEVER changes quality_status, never
   blocks approval, and never auto-deletes (user's Phase 5 rule #16: conservative,
   advisory/REVIEW metadata rather than automatic destruction).

No identity information is involved — this is image-redundancy detection only
(spec FR-013: no identity inference during quality validation).
"""

from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image

from app.config import QualityConfig

# pHash defaults follow contracts/photo-quality.md (research.md #5).
_HASH_SIZE = 16  # 16x16 low-frequency DCT block → 256 bits
_HIGHFREQ_FACTOR = 4  # resize to HASH_SIZE * HIGHFREQ = 64x64 before DCT


def content_sha256(data: bytes) -> str:
    """Deterministic exact-duplicate fingerprint of the raw uploaded bytes."""
    return hashlib.sha256(data).hexdigest()


def perceptual_hash(img: Image.Image, cfg: QualityConfig | None = None) -> int:
    """pHash of a decoded RGB image: DCT-II over a 64x64 grayscale downsample,
    median-threshold the top-left 16x16 low-frequency block → 256-bit int.

    Deterministic (pure numpy; no scipy dependency). Mirrors the imagehash pHash
    algorithm used in research.md #5.
    """
    size = _HASH_SIZE * _HIGHFREQ_FACTOR
    gray = img.convert("L").resize((size, size), Image.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float64)

    # 2D DCT-II via matrix multiplication (orthonormal basis).
    n = size
    basis = np.zeros((n, n), dtype=np.float64)
    for k in range(n):
        for x in range(n):
            basis[k, x] = np.cos(np.pi * (2 * x + 1) * k / (2 * n))
    basis[0] *= np.sqrt(1.0 / n)
    basis[1:] *= np.sqrt(2.0 / n)
    dct = basis @ pixels @ basis.T

    lowfreq = dct[:_HASH_SIZE, :_HASH_SIZE]
    median = np.median(lowfreq)
    bits = (lowfreq > median).flatten()
    return _bits_to_int(bits)


def _bits_to_int(bits: np.ndarray) -> int:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
    return value


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")