from abc import ABC, abstractmethod
from typing import List, Optional

from chat.domain.entities.skill import Skill, SkillMeta


class SkillRepository(ABC):
    """
    已发布 Skill 的 metadata 仓储接口
    """

    @abstractmethod
    async def list_skill_metas(self) -> List[SkillMeta]:
        """
        读取并返回全部 Skill 轻量元信息（不含 skill_md 与 assets_manifest 正文字段）
        """
        ...

    @abstractmethod
    async def get_published_skill(self, skill_id: str) -> Optional[Skill]:
        """
        按 skill_id 读取 Skill 完整文档并返回（含 skill_md + assets_manifest）
        """
        ...

    @abstractmethod
    async def upsert_published_skill(self, skill_published_message: dict) -> Optional[Skill]:
        """
        将 skill_published_message 写入数据库
        """
        ...

    @abstractmethod
    async def cache_skill_md(self, skill_id: str, skill_md: str) -> Optional[Skill]:
        """
        缓存 SKILL.md 正文
        """
        ...
