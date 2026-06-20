from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class UploadInitResponse:
    flash_uploaded: bool
    domain: str
    object_key: str
    put_url: str = ""
    callback_header: str = ""

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "UploadInitResponse":
        return cls(
            flash_uploaded=bool(payload.get("flashUploaded")),
            domain=str(payload.get("domain") or ""),
            object_key=str(payload.get("objectKey") or ""),
            put_url=str(payload.get("putUrl") or ""),
            callback_header=str(payload.get("callbackHeader") or ""),
        )


@dataclass(frozen=True)
class StorageRecord:
    object_key: str
    md5: str = ""
    size: int = 0
    file_id: Optional[int] = None
    domain: str = ""

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "StorageRecord":
        return cls(
            object_key=str(payload.get("objectKey") or ""),
            md5=str(payload.get("md5") or ""),
            size=int(payload.get("size") or 0),
            file_id=int(payload["fileId"]) if payload.get("fileId") is not None else None,
            domain=str(payload.get("domain") or ""),
        )
