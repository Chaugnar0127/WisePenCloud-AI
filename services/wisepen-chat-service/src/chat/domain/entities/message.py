from enum import Enum
import jieba
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field, BaseModel
from pymongo import IndexModel, ASCENDING

from chat.domain.entities.model import ModelFamily, ModelScope
from chat.domain.entities.provider import ProviderType
from chat.domain.repositories.model_repo import ModelRequestInfo


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallMessage(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MessageModelInfo(BaseModel):
    """消息持久化用的模型安全快照"""
    model_id: str
    provider_id: str
    provider_type: ProviderType
    model_family: ModelFamily
    model_name: str
    scope: ModelScope
    support_tools: bool
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    runtime_options: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_model_request(cls, model_request: ModelRequestInfo) -> "MessageModelInfo":
        return cls(
            model_id=str(model_request.model_id),
            provider_id=str(model_request.provider_id),
            provider_type=model_request.provider_type,
            model_family=model_request.model.model_family,
            model_name=model_request.model_name,
            scope=model_request.scope,
            support_tools=model_request.support_tools,
            context_window_tokens=model_request.context_window_tokens,
            max_output_tokens=model_request.max_output_tokens,
            runtime_options=model_request.runtime_options or {},
        )


class ChatMessage(Document):
    """单条消息实体（Beanie Document，映射到 chat_messages 集合）"""
    session_id: str
    role: Role # 消息标识

    # 生成该消息所用的模型安全快照，仅 assistant 消息必填
    model_info: Optional[MessageModelInfo] = None
    # 原生载荷，仅 assistant 消息必填
    provider_payload: Optional[Dict[str, Any]] = None  # LLMProvider的原生载荷，用于历史回放

    # 仅 tool 消息必填
    # 生成该消息所用的工具 tool_name 和 请求的 tool_call_id
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    # 工具消息的持久化占位器
    persisted_output_placeholder: str | None = Field(default=None, exclude=True)

    # 仅 assistant 消息必填
    reasoning_content: Optional[str] = None  # 大模型的推理/思考内容
    tool_calls: Optional[List[ToolCallMessage]] = None
    token_usage: int = 0

    content: Optional[str] = None   # 返回内容

    # 内容搜索分词，用于规避 MongoDB 中文分词缺陷
    content_search_tokens: Optional[str] = None

    # 元信息
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "wisepen_chat_message"  # MongoDB 集合名
        indexes = [
            # 按会话拉取历史记录的核心查询路径，防全表扫描
            IndexModel([("session_id", ASCENDING), ("created_at", ASCENDING)]),
            IndexModel([("content_search_tokens", "text")]),
        ]

    def build_search_tokens(self) -> None:
        """
        在保存前调用此方法。
        使用搜索引擎模式的分词（cut_for_search），最大化召回率。
        例如："软件工程架构" -> "软件 工程 软件工程 架构"
        """
        if self.content:
            # 过滤掉单字和标点符号，用空格拼接
            words = jieba.cut_for_search(self.content)
            self.content_search_tokens = " ".join([w for w in words if len(w.strip()) > 1])
