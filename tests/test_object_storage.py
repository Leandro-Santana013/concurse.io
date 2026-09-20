from services.object_storage import (
    ObjectStorageSettings,
    exam_pdf_object_key,
    get_object,
    question_object_key,
)


def test_object_storage_is_optional_without_server_secrets(monkeypatch):
    for name in (
        "OCI_OBJECT_STORAGE_NAMESPACE",
        "OCI_OBJECT_STORAGE_BUCKET",
        "OCI_OBJECT_STORAGE_REGION",
        "OCI_OBJECT_STORAGE_TENANCY",
        "OCI_OBJECT_STORAGE_USER",
        "OCI_OBJECT_STORAGE_FINGERPRINT",
        "OCI_OBJECT_STORAGE_PRIVATE_KEY",
        "OCI_OBJECT_STORAGE_PRIVATE_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = ObjectStorageSettings.from_environment()

    assert settings.configured is False
    assert get_object("questions/example.png") is None


def test_object_keys_are_stable_and_reject_paths():
    assert question_object_key("diagram.png") == "questions/diagram.png"
    assert exam_pdf_object_key(41, "prova") == "exams/41/prova.pdf"
    assert exam_pdf_object_key(41, "gabarito") == "exams/41/gabarito.pdf"

    try:
        question_object_key("../private.png")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal deveria ser rejeitado")
