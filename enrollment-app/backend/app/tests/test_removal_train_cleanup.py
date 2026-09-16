"""Regression test for the identity-removal train-cleanup defect (found during T035).

Defect: Frigate's `/api/faces/{name}/delete` removes an identity's *reference* crops but NOT
the identity-named *attempt* crops already saved under `faces/train/`. On a recognizer
rebuild, those leftover train crops reintroduced the deleted identity (observed: a deleted
throwaway identity re-recognized at ~1.0 and competed with a real enrolled person).

Fix under test: `FrigateEnrollmentService.remove_identity` now also purges ONLY the removed
identity's crops from `faces/train/` (identity-scoped, best-effort), so a rebuilt recognizer
cannot bring the deleted identity back.

Fully isolated: synthetic identity names only, a tmp faces dir, an in-memory fake transport.
No real Frigate, no real references, no network, no biometric content (files are empty stubs).
"""

from __future__ import annotations

from pathlib import Path

from app.config import FrigateConfig, Settings
from app.services.frigate_service import FrigateEnrollmentService

from app.tests.test_enrollment_service import FakeFrigateTransport


def _settings_with_faces_dir(tmp_path: Path) -> Settings:
    faces = tmp_path / "clips" / "faces"
    (faces / "train").mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=tmp_path / "data",
        frigate=FrigateConfig(
            enrollment_enabled=True,
            api_url="http://127.0.0.1:5001",
            faces_dir=str(faces),
        ),
    )


def _train(faces_dir: str) -> Path:
    return Path(faces_dir) / "train"


def _touch(train: Path, name: str) -> None:
    # Frigate attempt-crop shape: <start>-<trackid>-<ts>-<name>-<score>.webp
    (train / name).write_bytes(b"")  # empty stub — no biometric content


def test_remove_identity_purges_only_that_identitys_train_crops(tmp_path):
    settings = _settings_with_faces_dir(tmp_path)
    train = _train(settings.frigate.faces_dir)

    # Throwaway identity to remove, plus an unrelated identity and unknown crops.
    _touch(train, "1789507570.1-l6i0pc-1789507577.7-Throwaway_X-1.0.webp")
    _touch(train, "1789507595.8-lei4ki-1789507603.3-Throwaway_X-0.98.webp")
    _touch(train, "1789507621.6-0nbsde-1789507628.4-Other_Person-0.96.webp")
    _touch(train, "1789507647.1-h97tzh-1789507654.4-unknown-0.03.webp")
    _touch(train, "1789507660.2-zzz111-1789507666.9-unknown-0.webp")

    transport = FakeFrigateTransport()
    transport.library["Throwaway_X"] = ["Throwaway_X_1.webp"]
    transport.library["Other_Person"] = ["Other_Person_1.webp"]

    svc = FrigateEnrollmentService(settings=settings, transport=transport)
    result = svc.remove_identity("Throwaway_X")

    # exactly the two Throwaway_X train crops purged; nothing else touched.
    assert result.get("train_artifacts_purged") == 2
    remaining = sorted(p.name for p in train.iterdir())
    assert remaining == sorted([
        "1789507621.6-0nbsde-1789507628.4-Other_Person-0.96.webp",
        "1789507647.1-h97tzh-1789507654.4-unknown-0.03.webp",
        "1789507660.2-zzz111-1789507666.9-unknown-0.webp",
    ])
    # unrelated identity + unknown crops preserved
    assert not any("Throwaway_X" in n for n in remaining)


def test_deleted_identity_cannot_reappear_after_rebuild(tmp_path):
    """Simulate a recognizer rebuild (re-scan train/): the removed identity must have zero
    train crops, so it cannot be reintroduced."""
    settings = _settings_with_faces_dir(tmp_path)
    train = _train(settings.frigate.faces_dir)
    _touch(train, "1.1-aaa-2.2-Throwaway_X-1.0.webp")
    _touch(train, "1.1-bbb-2.2-Throwaway_X-0.97.webp")
    _touch(train, "1.1-ccc-2.2-unknown-0.01.webp")

    transport = FakeFrigateTransport()
    transport.library["Throwaway_X"] = ["Throwaway_X_1.webp"]
    svc = FrigateEnrollmentService(settings=settings, transport=transport)
    svc.remove_identity("Throwaway_X")

    # "rebuild" = re-scan train/ for any crop that would re-teach Throwaway_X
    reintroduce = [p.name for p in train.iterdir()
                   if FrigateEnrollmentService._train_crop_identity(p.name) == "Throwaway_X"]
    assert reintroduce == [], f"deleted identity would reappear via: {reintroduce}"


def test_hyphen_underscore_equivalence_in_train_names(tmp_path):
    """Frigate replaces '-' with '_' in the train-crop name field; removal by either form
    must still match (identity 'Foo-Bar' -> crops named 'Foo_Bar')."""
    settings = _settings_with_faces_dir(tmp_path)
    train = _train(settings.frigate.faces_dir)
    _touch(train, "1.1-aaa-2.2-Foo_Bar-0.95.webp")

    transport = FakeFrigateTransport()
    transport.library["Foo-Bar"] = ["Foo-Bar_1.webp"]
    svc = FrigateEnrollmentService(settings=settings, transport=transport)
    result = svc.remove_identity("Foo-Bar")

    assert result.get("train_artifacts_purged") == 1
    assert list(train.iterdir()) == []


def test_cleanup_skipped_safely_when_no_faces_dir(tmp_path):
    """With no faces_dir configured, removal still deletes references and reports 0 purged —
    never raises, never touches anything on disk."""
    settings = Settings(
        data_dir=tmp_path / "data",
        frigate=FrigateConfig(enrollment_enabled=True, faces_dir=""),
    )
    transport = FakeFrigateTransport()
    transport.library["Throwaway_X"] = ["Throwaway_X_1.webp"]
    svc = FrigateEnrollmentService(settings=settings, transport=transport)
    result = svc.remove_identity("Throwaway_X")
    assert result.get("train_artifacts_purged") == 0
    assert "Throwaway_X" not in transport.library  # reference delete still happened
