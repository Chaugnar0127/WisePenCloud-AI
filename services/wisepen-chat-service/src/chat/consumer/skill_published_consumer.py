from __future__ import annotations

from typing import Any

from common.logger import log_event

from chat.application.tools.skill_tools.utils.skill_cache_refresher import SkillCacheRefresher
from chat.domain.repositories import SkillRepository


class SkillPublishedConsumer:
    def __init__(
        self,
        *,
        skill_repo: SkillRepository,
        skill_cache_refresher: SkillCacheRefresher,
    ) -> None:
        self._skill_repo = skill_repo
        self._skill_cache_refresher = skill_cache_refresher

    async def handle(self, message: dict[str, Any]) -> None:
        skill = await self._skill_repo.upsert_published_skill(message)
        await self._skill_cache_refresher.trigger()
        log_event(
            "Skill 发布消息已同步",
            skill_id=skill.skill_id,
            version=skill.version,
            name=skill.name,
        )
