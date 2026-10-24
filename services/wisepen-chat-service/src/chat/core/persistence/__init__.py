from importlib import import_module
from typing import Any

# 单独使用 Mongo 仓储时不初始化 Redis/Nacos；容器仍可按原名称导入。
_modules = {
    "MongoMessageRepository": ".mongo.message_repository",
    "MongoSuspendedChatRepository": ".mongo.suspended_chat_repository",
    "MongoSessionRepository": ".mongo.session_repository",
    "MongoModelRepository": ".mongo.model_repository",
    "MongoProviderRepository": ".mongo.provider_repository",
    "MongoAdminModelRepository": ".mongo.admin_model_repository",
    "MongoToolConfigRepository": ".mongo.tool_config_repository",
    "MongoMcpServerConfigRepository": ".mongo.mcp_server_config_repository",
    "RedisHotContext": ".redis.hot_context",
    "RedisMcpToolDiscoveryCache": ".redis.mcp_tool_discovery_cache",
    "RedisChatTurnStream": ".redis.chat_turn_stream",
    "RedisToolContentRepository": ".redis.tool_content_repository",
}


def __getattr__(name: str) -> Any:
    if name not in _modules:
        raise AttributeError(name)
    value = getattr(import_module(_modules[name], __name__), name)
    globals()[name] = value
    return value


__all__ = [
    "MongoMessageRepository",
    "MongoSuspendedChatRepository",
    "MongoSessionRepository",
    "MongoModelRepository",
    "MongoProviderRepository",
    "MongoAdminModelRepository",
    "MongoToolConfigRepository",
    "MongoMcpServerConfigRepository",
    "RedisHotContext",
    "RedisMcpToolDiscoveryCache",
    "RedisChatTurnStream",
    "RedisToolContentRepository",
]
