from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List
from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel, ASCENDING


class SkillAssetMeta(BaseModel):
    """
    Skill Bundle 内单个附件的元信息
    仅描述"有哪些文件 / 什么用途 / 什么类型"，不存储文件
    实际正文由 SkillAssetLoader.load_by_object_key(object_key) / SkillAssetLoader.load_asset(skill_id, version, path) 按需懒加载
    """
    path: str = Field(..., description="作者视角的逻辑相对路径，出现在 assets_manifest 供 LLM 选择")
    object_key: str = Field(..., description="OSS 对象 key")
    kind: str = Field(..., description="资产类型 reference / template / script / example / other")
    description: str | None = Field(default="", description="对作者和 LLM 友好的简短说明，出现在 assets_manifest 里给模型看")
    size_bytes: int = Field(default=0, description="快照时记录的文件大小，便于治理与审计")


class Skill(Document):
    """
    已发布的 Skill 快照
    """

    skill_id: str = Field(...)
    name: str = Field(default="")
    description: str = Field(default="")
    source_type: str = Field(default="")

    skill_md: str = Field(default="", description="Cached SKILL.md body; empty until first authorized use downloads it")
    skill_md_object_key: str = Field(default="", description="SKILL.md object_key")
    assets_manifest: List[SkillAssetMeta] = Field(default_factory=list)

    version: int = Field(...)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "wisepen_published_skill"
        indexes = [
            IndexModel([("skill_id", ASCENDING)], unique=True),
        ]


@dataclass(frozen=True)
class SkillMeta:
    """
    Matcher / Coordinator 用的轻量元信息快照。
    """
    skill_id: str
    name: str
    description: str
    version: int
