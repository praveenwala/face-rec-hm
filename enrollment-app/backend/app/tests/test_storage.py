"""StorageService — private filesystem layout + traversal defense (T004, G1)."""

from __future__ import annotations

import uuid

import pytest

from app.exceptions import StorageError
from app.services.storage_service import StorageService


@pytest.fixture()
def storage(settings):
    return StorageService(settings)


def test_person_dir_uses_uuid_not_display_name(storage):
    person_id = str(uuid.uuid4())
    path = storage.person_dir(person_id)
    assert path.name == person_id
    assert path.parent.name == "people"
    assert storage.root in path.parents


def test_stored_filenames_are_randomized(storage):
    a = storage.make_stored_filename("Praveen.jpg")
    b = storage.make_stored_filename("Praveen.jpg")
    assert a != b
    assert a.endswith(".jpg")
    assert "Praveen" not in a
    # Unknown/absent extensions are dropped entirely: 32-hex UUID, no suffix.
    unknown = storage.make_stored_filename("photo.weird")
    assert len(unknown) == 32 and "." not in unknown
    noext = storage.make_stored_filename("noext")
    assert len(noext) == 32


def test_write_original_lands_inside_root(storage, tmp_path):
    person_id = str(uuid.uuid4())
    data = b"\xff\xd8\xff\xe0fakejpegbytes"
    target = storage.write_original(person_id, "whatever.jpg", data)
    assert target.read_bytes() == data
    assert storage.root.resolve() in target.resolve().parents


def test_traversal_rejected(storage):
    person_id = str(uuid.uuid4())
    # people/<uuid>/../../.. resolves above the data root (repo level) — must raise.
    with pytest.raises(StorageError):
        storage.resolve_inside("people", person_id, "..", "..", "..", "escape.txt")
    with pytest.raises(StorageError):
        storage.resolve_inside("../../etc/passwd")


def test_delete_photo_files_removes_all_copies(storage):
    person_id = str(uuid.uuid4())
    name = storage.make_stored_filename("a.jpg")
    for directory in ("original", "normalized", "approved"):
        path = storage.resolve_inside("people", person_id, directory, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    storage.delete_photo_files(person_id, name)
    for directory in ("original", "normalized", "approved"):
        assert not storage.resolve_inside("people", person_id, directory, name).exists()


def test_delete_person_files_removes_tree(storage):
    person_id = str(uuid.uuid4())
    original = storage.write_original(person_id, "a.jpg", b"x")
    assert original.exists()
    storage.delete_person_files(person_id)
    assert not storage.person_dir(person_id).exists()