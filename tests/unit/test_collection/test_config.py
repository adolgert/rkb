"""Tests for collection configuration loading."""

from pathlib import Path

from rkb.collection.config import CollectionConfig


def test_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PDF_LIBRARY_ROOT", raising=False)
    monkeypatch.delenv("PDF_CATALOG_DB", raising=False)
    monkeypatch.delenv("PDF_ZOTERO_STORAGE", raising=False)
    monkeypatch.delenv("PDF_BOX_STAGING", raising=False)
    monkeypatch.delenv("PDF_WORK_DOWNLOADS", raising=False)
    monkeypatch.delenv("PDF_MACHINE_ID", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_TYPE", raising=False)

    config = CollectionConfig.load()

    assert config.library_root == tmp_path / "Dropbox" / "findpdfs-library"
    assert config.catalog_db == config.library_root / "db" / "pdf_catalog.db"
    assert config.zotero_storage == tmp_path / "Zotero" / "storage"
    assert config.box_staging == tmp_path / "Documents" / "box-staging"
    assert config.work_downloads == tmp_path / "Downloads"
    assert config.zotero_library_id is None
    assert config.zotero_api_key is None
    assert config.zotero_library_type == "user"


def test_config_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(tmp_path / "custom-library"))
    monkeypatch.setenv("PDF_CATALOG_DB", str(tmp_path / "custom-library" / "db.sqlite"))
    monkeypatch.setenv("PDF_MACHINE_ID", "machine-test")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "12345")
    monkeypatch.setenv("ZOTERO_API_KEY", "secret-key")
    monkeypatch.setenv("ZOTERO_LIBRARY_TYPE", "group")

    config = CollectionConfig.load()

    assert config.library_root == tmp_path / "custom-library"
    assert config.catalog_db == tmp_path / "custom-library" / "db.sqlite"
    assert config.machine_id == "machine-test"
    assert config.zotero_library_id == "12345"
    assert config.zotero_api_key == "secret-key"
    assert config.zotero_library_type == "group"


def test_config_file_used_and_env_takes_precedence(monkeypatch, tmp_path):
    config_file = tmp_path / "collection.yaml"
    config_file.write_text(
        (
            "library_root: /yaml/library\n"
            "catalog_db: /yaml/library/db/catalog.sqlite\n"
            "machine_id: yaml-machine\n"
            "zotero_library_type: group\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("PDF_MACHINE_ID", "env-machine")

    config = CollectionConfig.load(config_path=config_file)

    assert config.library_root == Path("/yaml/library")
    assert config.catalog_db == Path("/yaml/library/db/catalog.sqlite")
    assert config.machine_id == "env-machine"
    assert config.zotero_library_type == "group"


def test_config_loads_library_root_config_yaml(monkeypatch, tmp_path):
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True)
    config_file = library_root / "config.yaml"
    config_file.write_text(
        (
            "catalog_db: /yaml/library/db/primary.sqlite\n"
            "machine_id: yaml-primary-machine\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    monkeypatch.delenv("PDF_MACHINE_ID", raising=False)
    monkeypatch.delenv("PDF_CATALOG_DB", raising=False)

    config = CollectionConfig.load()

    assert config.library_root == library_root
    assert config.catalog_db == Path("/yaml/library/db/primary.sqlite")
    assert config.machine_id == "yaml-primary-machine"
