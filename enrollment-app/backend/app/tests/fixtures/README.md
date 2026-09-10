# Test fixtures — provenance & licensing

Only ONE image is committed to this repository, and it is **not** a household or
biometric photo. It exists solely so the Phase 4 quality pipeline can be tested
against a real photographic face (YuNet does not detect synthetic/drawn faces).

## `astronaut.png`

- **Source**: scikit-image sample data (v0.24.0), downloaded from
  `https://raw.githubusercontent.com/scikit-image/scikit-image/v0.24.0/skimage/data/astronaut.png`
- **Content**: photograph of astronaut Eileen Collins (NASA)
- **License**: public domain — "No known copyright restrictions, released into
  the public domain" (NASA Great Images database; scikit-image documents it as
  such, see `skimage/data/README.txt`)
- **sha256**: `88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5`
- **Dimensions**: 512×512 RGB

## Derived fixtures

All other Phase 4 fixtures are derived from this image at test time (never
committed): resized (tiny face), composited (multiple faces), Gaussian-blurred
(TOO_BLURRY), and brightness-adjusted (UNDEREXPOSED / OVEREXPOSED). Solid-color
images are used for the NO_FACE case.