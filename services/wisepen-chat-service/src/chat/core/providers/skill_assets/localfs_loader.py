from __future__ import annotations

from pathlib import Path
from typing import Optional

from common.logger import log_event

from chat.core.providers.skill_assets.oss_loader import OssSkillAssetLoader
from chat.domain.interfaces.skill_asset_loader import SkillAssetLoader


class LocalFSSkillAssetLoader(SkillAssetLoader):
    """
    Dev-only Skill asset loader.

    Local fixtures use stable object keys:
    dev-fixtures/skills/<skill_id>/<relative_path>
    """

    _DEV_OBJECT_KEY_PREFIX = "dev-fixtures/skills/"

    def __init__(
        self,
        root_dir: str,
        *,
        oss_fallback: Optional[OssSkillAssetLoader] = None,
    ) -> None:
        self._root = Path(root_dir).resolve()
        self._oss = oss_fallback

    async def start(self) -> None:
        if self._oss is not None:
            await self._oss.start()

    async def stop(self) -> None:
        if self._oss is not None:
            await self._oss.stop()

    async def load_by_object_key(self, object_key: str) -> bytes:
        parsed_object_path = self._parse_dev_object_key(object_key)
        if parsed_object_path is not None:
            local_hit = self._try_read_local_file(parsed_object_path)
            if local_hit is not None: return local_hit
        else:
            log_event("Skill asset object_key is not a dev fixture key, fallback to OSS", object_key=object_key)
            oss_hit = await self._oss.load_by_object_key(object_key)
            if oss_hit is not None: return oss_hit

        raise FileNotFoundError(f"Skill asset not found.")

    def _parse_dev_object_key(self, object_key: str) -> Optional[tuple[str, str]]:
        if not object_key or not object_key.startswith(self._DEV_OBJECT_KEY_PREFIX):
            return None

        rel = object_key[len(self._DEV_OBJECT_KEY_PREFIX):]
        parts = rel.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None

        return parts[0], parts[1]

    def _try_read_local_file(self, parsed_object_path: tuple[str, str]) -> Optional[bytes]:
        skill_id, rel_path = parsed_object_path
        target_root = (self._root / skill_id).resolve()
        target = (target_root / rel_path).resolve()
        if target_root.parent != self._root:
            raise PermissionError(f"Asset skill_id escapes fixture root: {skill_id}")
        try:
            target.relative_to(target_root)
        except ValueError as exc:
            raise PermissionError(f"Asset path escapes skill asset root: {rel_path}") from exc
        if target == target_root:
            raise PermissionError(f"Asset path escapes skill asset root: {rel_path}")
        if not target.is_file():
            return None
        return target.read_bytes()
