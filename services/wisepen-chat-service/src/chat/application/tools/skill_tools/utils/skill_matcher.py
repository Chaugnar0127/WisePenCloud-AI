from abc import ABC, abstractmethod
from typing import List, Set

from common.logger import log_error

from chat.core.config.app_settings import settings
from chat.service_client import AIAssetClient
from chat.domain.entities.skill import SkillMeta


class SkillMatcher(ABC):
    """
    Skill 筛选器，返回当前请求可展示给 LLM 的 Skill 元信息
    """

    @abstractmethod
    async def match(self, self_selectable_skill_ids: Set[str], user_query: str) -> List[SkillMeta]: ...


class DefaultSkillMatcher(SkillMatcher):
    """
    默认 Skill 筛选器
    """

    def __init__(self, ai_asset_client: AIAssetClient) -> None:
        self._ai_asset_client = ai_asset_client

    async def match(self, self_selectable_skill_ids: Set[str], user_query: str) -> List[SkillMeta]:
        if not self_selectable_skill_ids:
            return []

        skill_meta_list:List[SkillMeta] = []
        try:
            skill_meta_list = await self._ai_asset_client.list_published_skills_meta(self_selectable_skill_ids)
        except Exception as e:
            log_error("Skill metadata resolve", e, count=len(self_selectable_skill_ids))

        top_k = max(1, settings.SKILL_MATCH_TOP_K)
        return skill_meta_list[:top_k]
