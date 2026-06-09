from abc import ABC, abstractmethod


class SkillAssetLoader(ABC):
    """
    Skill 附件的只读懒加载接口
    """

    @abstractmethod
    async def load_by_object_key(self, object_key: str) -> bytes:
        """按 OSS object_key 加载资产原始字节"""
        ...