# Pre-Development Setup & Validation Plan

**Feature**: [Front Door Person Identification](./spec.md)
**Gate**: Implementation MUST NOT begin until this validation gate passes (constitution Article XI.1 — requirements before implementation; Article V.1 — build incrementally).

## 1. Goal

Prove the local development environment, media pipeline, Frigate baseline, MQTT transport,
and Home Assistant integration independently — each on its own — before any identity-logic
code is written.

## 2. Required Local Tools

| Tool | Purpose | Validation |
|---|---|---|
| Docker Desktop | Run Frigate and supporting services | `docker version` works |
| Docker Compose | Reproducible local services | `docker compose version` works |
| Git | Project/version control | `git --version` works |
| curl | HTTP/API reachability tests | `curl --version` works |
| ffprobe | Inspect sample media | Can probe one image and one video |
| VLC or ffplay | Verify RTSP/video independently of Frigate | Test stream plays |
| MQTT client | Broker pub/sub smoke test | Test message round-trip succeeds |
| Frigate | Person detection and face recognition platform | Container healthy and UI reachable |

## 3. Validation Order

1. Inventory Mac hardware and architecture.
2. Validate Docker and Compose.
3. Validate network reachability to Home Assistant.
4. Validate MQTT publish/subscribe.
5. Start Frigate with minimal config.
6. Validate Frigate UI and logs.
7. Validate one local/test media source.
8. Validate person detection.
9. Connect Home Assistant to Frigate.
10. Confirm existing Ring automations still work.
11. Only then add Ring-MQTT/live Ring stream.
12. Only then enable face recognition on supported hardware.

## 4. Detailed Gate Criteria (PD-01 – PD-10)

### PD-01 — Host Capability Inventory

The development host MUST be inventoried before dependencies are installed. Record:

- Mac model
- CPU architecture: Intel or Apple Silicon
- macOS version
- available RAM
- available free disk space
- Docker Desktop version
- Docker architecture
- network path to Home Assistant
- whether the host can reach the Home Assistant MQTT broker
- whether the host can reach the intended Front Door stream endpoint once Ring video
  bridging is configured

The project MUST NOT assume support for a hardware-specific detector or face-recognition
backend before verifying the host architecture.

> Already inventoried during `/grill-me` for this feature: Intel Mac, confirmed via
> `sysctl -n machdep.cpu.brand_string` → `Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz`,
> `uname -m` → `x86_64`.

### PD-02 — Required Local Runtime

Before feature implementation, the development environment MUST have working installations
of: Docker Desktop, Docker Compose support, Git, curl, an RTSP/video test client such as VLC
or ffplay, ffprobe for media inspection, access to an MQTT client for publish/subscribe
validation, and a local project directory with configuration, tests, and sample-media
folders.

Frigate itself SHOULD run in Docker rather than requiring the project developer to install
Frigate's Python dependencies directly on macOS.

### PD-03 — MQTT Validation

Before connecting Frigate:

1. The Mac MUST be able to reach the MQTT broker.
2. A test client MUST successfully subscribe to a test topic.
3. A second client MUST successfully publish a test message.
4. The subscribed client MUST receive the exact test message.
5. Authentication and TLS settings, when used, MUST be documented.

### PD-04 — Container Validation

Before adding camera or recognition configuration:

1. Docker MUST start successfully.
2. A test container MUST execute successfully.
3. Docker Compose MUST create and remove a simple test service.
4. Required project directories MUST mount into a container correctly.
5. Container logs MUST be readable from the Mac.

### PD-05 — Frigate Baseline Validation

Before connecting Ring:

1. Frigate MUST start using a minimal configuration.
2. The Frigate UI MUST be reachable locally.
3. The container MUST remain healthy without restart loops.
4. Logs MUST show no unresolved configuration errors.
5. MQTT availability MUST be verified if MQTT is enabled.
6. A test camera/media source MUST be ingestible.

### PD-06 — Media Validation

Before testing AI behavior, every supplied test image or video MUST pass media inspection.
For each file the validation tool MUST record: filename, detected container/format, codec
when applicable, width and height, frame rate when applicable, duration when applicable,
whether decoding succeeds, and whether normalization is required.

Files that cannot be decoded MUST be rejected with a clear reason rather than silently
skipped.

### PD-07 — Person Detection Validation

Before enabling identity recognition:

1. A test video containing a person MUST be ingested.
2. Frigate MUST produce a person detection.
3. A test video without a person MUST NOT produce a false identity event.
4. Event timing and logs MUST be inspectable.

### PD-08 — Home Assistant Integration Validation

Before adding identity notifications:

1. Frigate and Home Assistant MUST use the same MQTT broker.
2. Home Assistant MUST be able to connect to the Frigate instance.
3. At least one Frigate-generated event/entity MUST be visible in Home Assistant.
4. Existing Ring doorbell and motion automations MUST continue to work independently.

### PD-09 — Face Recognition Hardware Gate

Native Frigate face recognition MUST only be enabled on hardware that satisfies Frigate's
documented requirements.

If the local Mac does not satisfy the current face-recognition requirements, the local Mac
test MUST stop at stream ingestion, person detection, MQTT, and Home Assistant integration.
Face-recognition validation MUST then be performed on a supported host.

> Resolved during `/grill-me` for this feature: the confirmed Intel dev host satisfies
> Frigate's x86 AVX/AVX2 requirement, so this gate is expected to pass on the same machine —
> it still MUST be explicitly re-verified against Frigate's documented requirements at PD-09
> time, not assumed from the CPU check alone.

### PD-10 — No Development Before Green Baseline

The first feature implementation task may begin only after PD-01 through PD-08 pass, and
PD-09 has either passed or has been explicitly deferred to supported hardware.

A validation report MUST be stored in the project before implementation begins.

## 5. Sample Media to Request

### Photos

Provide **5-10 sample photos** of the first known person to enroll:

- 2-3 clear front-facing daylight photos
- 1-2 indoor photos
- 1-2 slightly different facial expressions
- 1 photo with a mild left/right angle
- optional later samples from the actual Front Door camera

Do not start with a very large bulk photo library. Photos SHOULD avoid: heavy blur, extreme
under/overexposure, very small faces, severe occlusion, sunglasses/hat combinations in the
initial foundation set, and multiple people in the same training image when a single-person
image is available.

### Videos

Provide **3-5 short clips** (approximately 5-30 seconds each) for local testing:

1. one known person walking toward the camera
2. one unknown/untrained person walking toward the camera
3. one clip with no person but ordinary scene motion
4. one lower-light or evening person clip
5. optional clip with two people

### Media Privacy

Sample media MUST contain only people the user is authorized to use for this household test.
Test media containing biometric data SHOULD remain outside public source control — consistent
with constitution Principles II.4 and II.5.

## 6. Media Format Compatibility Policy

The system MUST support broad media compatibility, but the project MUST NOT claim literal
support for every image or video format in existence. The media-ingestion test harness MUST
accept any file format that can be successfully decoded by the installed FFmpeg/image
decoding stack, determined by actually probing/decoding the file (e.g. via ffprobe) rather
than trusting the filename extension.

Common image inputs SHOULD include, where supported by the installed decoder: JPEG/JPG, PNG,
WEBP, BMP, GIF, TIFF, AVIF. HEIC/HEIF MUST be treated as conditional support — current Frigate
Face Library uploads do not support HEIC directly, so HEIC inputs intended for training MUST
be converted to a supported format such as JPEG before upload.

Common video containers SHOULD include, where decodable: MP4, MOV, MKV, AVI, MPEG/MPG, WebM,
M4V, TS/MTS when supported by the installed FFmpeg build. Common video codecs SHOULD include,
where decodable: H.264/AVC, H.265/HEVC, MPEG-4, MPEG-2, VP8, VP9, AV1, MJPEG.

To isolate the AI pipeline from file-format differences, the local test harness SHOULD
normalize supported source media into canonical test formats: training/test images as JPEG or
PNG, test videos as MP4 with H.264 video, and extracted frames as JPEG or PNG. The original
file MUST be retained separately during testing when privacy policy permits.

The test harness MUST: (1) probe the input, (2) attempt decoding, (3) normalize when
necessary, (4) report unsupported media clearly, and (5) never classify a failed decode as an
AI detection failure.

## 7. Pre-Development Dependency Set

**Required**: Docker Desktop, Docker Compose, Git, Frigate container image, MQTT broker
access, Home Assistant MQTT integration, Home Assistant Frigate integration, ffmpeg/ffprobe
capability (via the Frigate container and/or local tooling for validation), VLC or ffplay for
stream verification, an MQTT CLI/client for diagnostic publish/subscribe testing, Ring-MQTT or
another supported Ring video bridge before live Ring stream testing, and go2rtc where required
by the selected video path.

**Conditional**: an Apple Silicon detector client for Frigate object detection on supported
Apple Silicon Macs, a supported accelerator/GPU/NPU for production AI workloads, a dedicated
production AI host, and image-conversion support for formats not directly accepted by the Face
Library.

**Not required as host Python libraries**: the baseline architecture MUST NOT require manually
installing Frigate's internal Python libraries into the Mac's system Python environment.
Containerized dependencies MUST remain inside their container unless a documented host-side
component explicitly requires installation.

## 8. Exit Criteria

Implementation can start only when:

- Docker works
- Compose works
- MQTT pub/sub works
- Frigate starts cleanly
- test media decodes
- person detection works
- Home Assistant sees Frigate data
- existing Ring automations remain unaffected
- face-recognition hardware compatibility is confirmed or explicitly deferred to supported
  hardware
- a validation report documenting the above has been stored in the project
