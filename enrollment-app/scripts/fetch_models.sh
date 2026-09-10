#!/usr/bin/env bash
# Fetch the face-detection model into the app's private (gitignored) runtime cache.
#
# Model: facedet.onnx — YuNet face detector (OpenCV FaceDetectorYN), the Frigate-aligned
# facedet.onnx used by the validated local Frigate 0.17.2 environment
# (frigate/data_processing/real_time/face.py). No broader compatibility with every Frigate
# installation/version is claimed — only the locally validated 0.17.2 environment.
#
# Provenance:
#   - Packaged by NickM-27/facenet-onnx (Apache-2.0), release v1.0 — the same release
#     the validated Frigate 0.17.2 environment downloads:
#     https://github.com/NickM-27/facenet-onnx/releases/download/v1.0/facedet.onnx
#   - Also present on this host in Frigate's model cache: frigate/config/model_cache/facedet/facedet.onnx
#   - sha256 (verified): 321aa5a6afabf7ecc46a3d06bfab2b579dc96eb5c3be7edd365fa04502ad9294
#
# The app never depends on the Frigate container being up: it prefers the local Frigate
# cache copy if present, otherwise downloads from the canonical GitHub release URL, and
# always verifies the checksum. No model binary is ever committed to git.

set -euo pipefail

EXPECTED_SHA256="321aa5a6afabf7ecc46a3d06bfab2b579dc96eb5c3be7edd365fa04502ad9294"
DOWNLOAD_URL="https://github.com/NickM-27/facenet-onnx/releases/download/v1.0/facedet.onnx"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODEL_DIR="${APP_DIR}/data/models"
TARGET="${MODEL_DIR}/facedet.onnx"

LOCAL_FRIGATE_CACHE="${APP_DIR}/../frigate/config/model_cache/facedet/facedet.onnx"

mkdir -p "${MODEL_DIR}"

if [[ -f "${TARGET}" ]] && [[ "$(shasum -a 256 "${TARGET}" | awk '{print $1}')" == "${EXPECTED_SHA256}" ]]; then
    echo "[fetch_models] ${TARGET} already present and verified — nothing to do."
    exit 0
fi

if [[ -f "${LOCAL_FRIGATE_CACHE}" ]] && [[ "$(shasum -a 256 "${LOCAL_FRIGATE_CACHE}" | awk '{print $1}')" == "${EXPECTED_SHA256}" ]]; then
    echo "[fetch_models] copying from local Frigate cache: ${LOCAL_FRIGATE_CACHE}"
    cp "${LOCAL_FRIGATE_CACHE}" "${TARGET}"
else
    echo "[fetch_models] downloading ${DOWNLOAD_URL}"
    curl -fL --retry 3 -o "${TARGET}" "${DOWNLOAD_URL}"
fi

ACTUAL="$(shasum -a 256 "${TARGET}" | awk '{print $1}')"
if [[ "${ACTUAL}" != "${EXPECTED_SHA256}" ]]; then
    echo "[fetch_models] ERROR: checksum mismatch — expected ${EXPECTED_SHA256}, got ${ACTUAL}" >&2
    rm -f "${TARGET}"
    exit 1
fi

echo "[fetch_models] OK: ${TARGET} (sha256 ${ACTUAL})"