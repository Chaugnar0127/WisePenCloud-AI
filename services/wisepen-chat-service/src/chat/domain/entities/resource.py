from dataclasses import dataclass, field
from typing import Any, Mapping


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if item is not None)


@dataclass(frozen=True)
class ResourcePermission:
    resource_access_role: str = ""
    permission_sources: tuple[str, ...] = field(default_factory=tuple)
    allowed_actions: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "ResourcePermission":
        return cls(
            resource_access_role=str(payload.get("resourceAccessRole") or ""),
            permission_sources=_string_tuple(payload.get("permissionSources")),
            allowed_actions=_string_tuple(payload.get("allowedActions")),
        )

    def allows(self, action: str) -> bool:
        return action in self.allowed_actions


@dataclass(frozen=True)
class ResourceItemInfo:
    resource_id: str
    resource_name: str = ""
    resource_type: str = ""
    owner_id: str = ""
    preview: str = ""
    size: int = 0
    current_actions: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "ResourceItemInfo":
        return cls(
            resource_id=str(payload.get("resourceId") or ""),
            resource_name=str(payload.get("resourceName") or ""),
            resource_type=str(payload.get("resourceType") or ""),
            owner_id=str(payload.get("ownerId") or ""),
            preview=str(payload.get("preview") or ""),
            size=int(payload.get("size") or 0),
            current_actions=_string_tuple(payload.get("currentActions")),
        )
