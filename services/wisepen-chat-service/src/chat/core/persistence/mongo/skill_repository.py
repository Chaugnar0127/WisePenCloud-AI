from datetime import datetime, timezone
from typing import Any, List, Optional

from chat.service_client import AIAssetClient
from common.logger import log_error, log_fail

from chat.domain.entities.skill import Skill, SkillAssetMeta, SkillMeta
from chat.domain.repositories import SkillRepository


class MongoSkillRepository(SkillRepository):
    """
    SkillRepository 的 MongoDB (Beanie) 实现
    """

    def __init__(self, ai_asset_client: AIAssetClient) -> None:
        self._ai_asset_client = ai_asset_client

    async def list_skill_metas(self) -> List[SkillMeta]:
        docs = await Skill.find_all().to_list()
        return [
            SkillMeta(
                skill_id=doc.skill_id,
                name=doc.name,
                description=doc.description,
                version=doc.version,
            )
            for doc in docs
        ]

    async def get_published_skill(self, skill_id: str) -> Optional[Skill]:
        skill = await Skill.find_one(Skill.skill_id == skill_id)
        if skill is not None: return skill
        try:
            published_skill_res = await self._ai_asset_client.get_published_skill_by_resource_id(skill_id)
        except Exception as e:
            log_error("ai-asset published skill 回源", e, skill_id=skill_id)
            raise
        if not published_skill_res: return None
        return await self.upsert_published_skill(published_skill_res)

    async def upsert_published_skill(self, published_skill_res: dict) -> Optional[Skill]:
        skill_id = str(published_skill_res.get("resourceId")).strip()
        latest_published_skill = published_skill_res.get("latestPublishedSkill")

        skill = await Skill.find_one(Skill.skill_id == skill_id)
        now = datetime.now(timezone.utc)

        # 如果 skill 不存在则新增
        if skill is None:
            skill = Skill(skill_id=skill_id, created_at=now, version=0)

        # 版本未变更，无需更新 skill
        if int(latest_published_skill.get("version")) == skill.version:
            return skill

        skill.name=str(published_skill_res.get("name"))
        skill.description=str(published_skill_res.get("description"))
        skill.source_type=str(published_skill_res.get("sourceType"))
        skill.version=int(latest_published_skill.get("version"))
        skill.skill_md=""
        skill.skill_md_object_key=str(latest_published_skill.get("mainSkillMD").get("objectKey"))
        skill.assets_manifest = []
        skill.updated_at=now

        for item in latest_published_skill.get("skillAssets"):
            skill.assets_manifest.append(
                SkillAssetMeta(
                    path=f"{item.get('path').strip('/')}/{item.get('name')}",
                    object_key=item.get("objectKey"),
                    kind=str(item.get("skillAssetResourceType")),
                    description=None,
                    size_bytes=int(item.get("size") or 0),
                )
            )

        await skill.save()
        return skill

    async def cache_skill_md(self, skill_id: str, skill_md: str) -> Optional[Skill]:
        skill = await Skill.find_one(Skill.skill_id == skill_id)
        skill.skill_md = skill_md
        skill.updated_at = datetime.now(timezone.utc)
        await skill.save()
        return skill
