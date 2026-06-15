import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any


IMAGE_ENRICHMENT_FILENAME = "image-enrichment.json"
IMAGE_ENRICHMENT_SCHEMA_VERSION = 1
IMAGE_ENRICHMENT_CONFIDENCES = {"high", "medium", "low"}
IMAGE_ENRICHMENT_VISUAL_TYPES = {"diagram", "chart", "screenshot", "photo", "other"}


@dataclass(frozen=True)
class ImageEnrichmentIssue:
    code: str
    message: str
    asset_path: str | None = None
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.asset_path is not None:
            payload["asset_path"] = self.asset_path
        if self.index is not None:
            payload["index"] = self.index
        return payload


@dataclass(frozen=True)
class ImageEnrichmentEntry:
    asset_path: str
    vision_summary: str | None = None
    ocr_text: str | None = None
    visual_type: str | None = None
    key_elements: list[str] = field(default_factory=list)
    confidence: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None

    @property
    def is_failed(self) -> bool:
        return self.failure_code is not None

    def artifact_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "status": "failed" if self.is_failed else "matched",
            "asset_path": self.asset_path,
        }
        if self.is_failed:
            metadata["failure_code"] = self.failure_code
            if self.failure_message:
                metadata["failure_message"] = self.failure_message
            return metadata
        if self.visual_type:
            metadata["visual_type"] = self.visual_type
        if self.key_elements:
            metadata["key_elements"] = self.key_elements
        if self.confidence:
            metadata["confidence"] = self.confidence
        return metadata


@dataclass(frozen=True)
class ImageEnrichmentSidecar:
    status: str
    entries_by_asset_path: dict[str, ImageEnrichmentEntry] = field(default_factory=dict)
    issues: list[ImageEnrichmentIssue] = field(default_factory=list)
    content_sha256: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "status": self.status,
            "sidecar_filename": IMAGE_ENRICHMENT_FILENAME,
            "entry_count": len(self.entries_by_asset_path),
        }
        if self.content_sha256 is not None:
            metadata["content_sha256"] = self.content_sha256
        if self.issues:
            metadata["issues"] = [issue.to_dict() for issue in self.issues]
        return metadata


def load_image_enrichment_sidecar(document_path: Path) -> ImageEnrichmentSidecar:
    sidecar_path = document_path.parent / IMAGE_ENRICHMENT_FILENAME
    if not sidecar_path.exists():
        return ImageEnrichmentSidecar(status="missing")
    try:
        content_bytes = sidecar_path.read_bytes()
    except OSError:
        return ImageEnrichmentSidecar(
            status="invalid",
            issues=[
                ImageEnrichmentIssue(
                    code="image_enrichment_read_failed",
                    message="image enrichment sidecar could not be read",
                )
            ],
        )
    try:
        payload = json.loads(content_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ImageEnrichmentSidecar(
            status="invalid",
            content_sha256=sha256(content_bytes).hexdigest(),
            issues=[
                ImageEnrichmentIssue(
                    code="invalid_image_enrichment_json",
                    message="image enrichment sidecar is not valid JSON",
                )
            ],
        )

    if not isinstance(payload, dict):
        return _invalid_sidecar(content_bytes, "invalid_image_enrichment_shape", "sidecar root must be an object")
    if payload.get("schema_version") != IMAGE_ENRICHMENT_SCHEMA_VERSION:
        return _invalid_sidecar(
            content_bytes,
            "unsupported_image_enrichment_schema",
            "sidecar schema_version must be 1",
        )
    images = payload.get("images")
    if not isinstance(images, list):
        return _invalid_sidecar(content_bytes, "invalid_image_enrichment_images", "sidecar images must be a list")

    entries: dict[str, ImageEnrichmentEntry] = {}
    issues: list[ImageEnrichmentIssue] = []
    for index, raw_entry in enumerate(images):
        entry, entry_issues = _parse_image_entry(raw_entry, index)
        issues.extend(entry_issues)
        if entry is None:
            continue
        entries[entry.asset_path] = entry
    return ImageEnrichmentSidecar(
        status="loaded",
        entries_by_asset_path=entries,
        issues=issues,
        content_sha256=sha256(content_bytes).hexdigest(),
    )


def normalize_enrichment_asset_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _invalid_sidecar(content_bytes: bytes, code: str, message: str) -> ImageEnrichmentSidecar:
    return ImageEnrichmentSidecar(
        status="invalid",
        content_sha256=sha256(content_bytes).hexdigest(),
        issues=[ImageEnrichmentIssue(code=code, message=message)],
    )


def _parse_image_entry(raw_entry: object, index: int) -> tuple[ImageEnrichmentEntry | None, list[ImageEnrichmentIssue]]:
    issues: list[ImageEnrichmentIssue] = []
    if not isinstance(raw_entry, dict):
        return None, [
            ImageEnrichmentIssue(
                code="invalid_image_enrichment_entry",
                message="image enrichment entry must be an object",
                index=index,
            )
        ]

    raw_asset_path = _optional_str(raw_entry.get("asset_path"))
    if raw_asset_path is None:
        return None, [
            ImageEnrichmentIssue(
                code="missing_image_enrichment_asset_path",
                message="image enrichment entry is missing asset_path",
                index=index,
            )
        ]
    asset_path = normalize_enrichment_asset_path(raw_asset_path)
    failure_code, failure_message = _failure_fields(raw_entry)
    if failure_code is not None:
        return (
            ImageEnrichmentEntry(
                asset_path=asset_path,
                failure_code=failure_code,
                failure_message=failure_message,
            ),
            issues,
        )

    vision_summary = _optional_str(raw_entry.get("vision_summary"))
    if vision_summary is None:
        return (
            ImageEnrichmentEntry(
                asset_path=asset_path,
                failure_code="missing_vision_summary",
                failure_message="image enrichment entry is missing vision_summary",
            ),
            [
                ImageEnrichmentIssue(
                    code="missing_vision_summary",
                    message="image enrichment entry is missing vision_summary",
                    asset_path=asset_path,
                    index=index,
                )
            ],
        )

    visual_type = _enum_value(raw_entry.get("visual_type"), IMAGE_ENRICHMENT_VISUAL_TYPES)
    confidence = _enum_value(raw_entry.get("confidence"), IMAGE_ENRICHMENT_CONFIDENCES)
    return (
        ImageEnrichmentEntry(
            asset_path=asset_path,
            vision_summary=vision_summary,
            ocr_text=_optional_str(raw_entry.get("ocr_text")),
            visual_type=visual_type,
            key_elements=_string_list(raw_entry.get("key_elements")),
            confidence=confidence,
        ),
        issues,
    )


def _failure_fields(raw_entry: dict[str, Any]) -> tuple[str | None, str | None]:
    failure = raw_entry.get("failure")
    if isinstance(failure, dict):
        code = _optional_str(failure.get("code"))
        message = _optional_str(failure.get("message"))
        if code is not None:
            return code, message
    return _optional_str(raw_entry.get("failure_code")), _optional_str(raw_entry.get("failure_message"))


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _enum_value(value: object, allowed: set[str]) -> str | None:
    normalized = _optional_str(value)
    if normalized in allowed:
        return normalized
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _optional_str(item)
        if text is not None:
            result.append(text)
    return result
