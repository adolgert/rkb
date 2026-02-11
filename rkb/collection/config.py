"""Configuration loading for collection workflows."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

import yaml

_ENV_TO_FIELD = {
    "PDF_LIBRARY_ROOT": "library_root",
    "PDF_CATALOG_DB": "catalog_db",
    "PDF_ZOTERO_STORAGE": "zotero_storage",
    "PDF_BOX_STAGING": "box_staging",
    "PDF_WORK_DOWNLOADS": "work_downloads",
    "PDF_MACHINE_ID": "machine_id",
    "ZOTERO_LIBRARY_ID": "zotero_library_id",
    "ZOTERO_API_KEY": "zotero_api_key",
    "ZOTERO_LIBRARY_TYPE": "zotero_library_type",
}


def _as_path(value: str | Path) -> Path:
    return Path(value).expanduser()


@dataclass
class CollectionConfig:
    """Resolved configuration for collection modules."""

    library_root: Path
    catalog_db: Path
    zotero_storage: Path
    box_staging: Path
    work_downloads: Path
    machine_id: str
    zotero_library_id: str | None
    zotero_api_key: str | None
    zotero_library_type: str

    @classmethod
    def load(cls, config_path: Path | None = None) -> CollectionConfig:
        """Load config with precedence: defaults < YAML < environment."""
        default_library_root = _as_path("~/Dropbox/findpdfs-library")
        library_root_env = os.environ.get("PDF_LIBRARY_ROOT")
        resolved_library_root = (
            _as_path(library_root_env) if library_root_env else default_library_root
        )

        values: dict[str, str | Path | None] = {
            "library_root": resolved_library_root,
            "catalog_db": resolved_library_root / "db" / "pdf_catalog.db",
            "zotero_storage": _as_path("~/Zotero/storage"),
            "box_staging": _as_path("~/Documents/box-staging"),
            "work_downloads": _as_path("~/Downloads"),
            "machine_id": socket.gethostname(),
            "zotero_library_id": None,
            "zotero_api_key": None,
            "zotero_library_type": "user",
        }

        yaml_values = cls._load_yaml_values(
            config_path=config_path,
            library_root=resolved_library_root,
        )
        values.update(yaml_values)

        for env_key, field_name in _ENV_TO_FIELD.items():
            env_value = os.environ.get(env_key)
            if env_value is None or env_value == "":
                continue
            values[field_name] = env_value

        path_fields = {
            "library_root",
            "catalog_db",
            "zotero_storage",
            "box_staging",
            "work_downloads",
        }
        for path_field in path_fields:
            values[path_field] = _as_path(values[path_field])  # type: ignore[arg-type]

        zotero_library_id = values["zotero_library_id"] or None
        zotero_api_key = values["zotero_api_key"] or None

        return cls(
            library_root=values["library_root"],  # type: ignore[arg-type]
            catalog_db=values["catalog_db"],  # type: ignore[arg-type]
            zotero_storage=values["zotero_storage"],  # type: ignore[arg-type]
            box_staging=values["box_staging"],  # type: ignore[arg-type]
            work_downloads=values["work_downloads"],  # type: ignore[arg-type]
            machine_id=str(values["machine_id"]),
            zotero_library_id=str(zotero_library_id) if zotero_library_id else None,
            zotero_api_key=str(zotero_api_key) if zotero_api_key else None,
            zotero_library_type=str(values["zotero_library_type"]),
        )

    @classmethod
    def _load_yaml_values(
        cls,
        config_path: Path | None,
        library_root: Path,
    ) -> dict[str, str | Path | None]:
        candidates = (
            [config_path.expanduser()]
            if config_path is not None
            else [library_root / "config.yaml", _as_path("~/.config/rkb/collection.yaml")]
        )

        for candidate in candidates:
            if not candidate.exists():
                continue

            with candidate.open("r", encoding="utf-8") as config_file:
                loaded = yaml.safe_load(config_file) or {}
            if not isinstance(loaded, dict):
                return {}

            allowed_keys = {
                "library_root",
                "catalog_db",
                "zotero_storage",
                "box_staging",
                "work_downloads",
                "machine_id",
                "zotero_library_id",
                "zotero_api_key",
                "zotero_library_type",
            }
            return {key: value for key, value in loaded.items() if key in allowed_keys}

        return {}
