"""
Seed local dev Skill fixtures into the chat-service read model.

Fixture layout:
    dev_fixtures/skill_bundles/<skill_id>/SKILL.md
    dev_fixtures/skill_bundles/<skill_id>/<asset files...>

In local fixtures, skill_id is a stand-in for Java ai-asset resourceId.
The local test version is always -1.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import yaml
from beanie import init_beanie
from pymongo import AsyncMongoClient

from common.logger import log_error, log_event

from chat.domain.entities.skill import Skill, SkillAssetMeta


_DEV_SKILL_VERSION = -1
_DEV_OBJECT_KEY_PREFIX = "dev-fixtures/skills"


def _object_key(skill_id: str, rel_path: str) -> str:
    return f"{_DEV_OBJECT_KEY_PREFIX}/{skill_id}/{rel_path}"


def _split_frontmatter(text: str) -> Tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    fm_text = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1:])
    meta = yaml.safe_load(fm_text) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def _scan_assets(skill_dir: Path, skill_id: str) -> List[SkillAssetMeta]:
    assets: List[SkillAssetMeta] = []
    for p in sorted(skill_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(skill_dir).as_posix()
        if rel == "SKILL.md":
            continue
        assets.append(
            SkillAssetMeta(
                path=rel,
                object_key=_object_key(skill_id, rel),
                kind="other",
                description="(dev fixture, no description)",
                size_bytes=p.stat().st_size,
            )
        )
    return assets


async def _seed_one_skill(skill_dir: Path) -> bool:
    skill_id = skill_dir.name
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        log_error(
            "seed_demo_skills: skip, missing SKILL.md",
            FileNotFoundError(str(skill_md_path)),
            skill_id=skill_id,
        )
        return False

    raw = skill_md_path.read_text(encoding="utf-8")
    meta, _body = _split_frontmatter(raw)
    name = meta.get("name") or skill_id
    description = meta.get("description") or ""

    assets_manifest = _scan_assets(skill_dir, skill_id=skill_id)
    skill_md_object_key = _object_key(skill_id, "SKILL.md")

    existing = await Skill.find_one(Skill.skill_id == skill_id)
    now = datetime.now(timezone.utc)
    if existing is None:
        doc = Skill(
            skill_id=skill_id,
            name=name,
            description=description,
            source_type="DEV_FIXTURE",
            skill_md=raw,
            skill_md_object_key=skill_md_object_key,
            assets_manifest=assets_manifest,
            version=_DEV_SKILL_VERSION,
            created_at=now,
            updated_at=now,
        )
        await doc.insert()
        log_event("seed_demo_skills: insert", skill_id=skill_id, assets=len(assets_manifest))
    else:
        existing.name = name
        existing.description = description
        existing.source_type = "DEV_FIXTURE"
        existing.skill_md = raw
        existing.skill_md_object_key = skill_md_object_key
        existing.assets_manifest = assets_manifest
        existing.version = _DEV_SKILL_VERSION
        existing.updated_at = now
        await existing.save()
        log_event("seed_demo_skills: update", skill_id=skill_id, assets=len(assets_manifest))
    return True


async def _main() -> None:
    default_root = Path(__file__).resolve().parents[3] / "dev_fixtures" / "skill_bundles"
    root = Path(os.environ.get("SKILL_ASSETS_CACHE_PATH", str(default_root))).resolve()
    if not root.is_dir():
        log_error(
            "seed_demo_skills: SKILL_ASSETS_CACHE_PATH does not exist",
            FileNotFoundError(str(root)),
            path=str(root),
        )
        return

    mongo_url = os.environ.get("SEED_MONGO_URL", "mongodb://root:root@localhost:27017/")
    mongo_db = os.environ.get("SEED_MONGO_DB", "wisepen_chat")
    mongo_client = AsyncMongoClient(mongo_url)
    await init_beanie(
        database=mongo_client[mongo_db],
        document_models=[Skill],
    )

    seeded = 0
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if await _seed_one_skill(skill_dir):
            seeded += 1

    log_event("seed_demo_skills: done", skills=seeded, root=str(root), version=_DEV_SKILL_VERSION)


if __name__ == "__main__":
    asyncio.run(_main())
