# src/chat/container.py

from typing import List

from dependency_injector import containers, providers
from v2.nacos import NacosNamingService

from chat.consumer.skill_published_consumer import SkillPublishedConsumer
from chat.core.config.app_settings import settings
from chat.core.config.bootstrap_settings import bootstrap_settings
from chat.core.providers import (
    LiteLLMAdapter,
    Mem0Adapter,
    LocalFSSkillAssetLoader,
    OssSkillAssetLoader,
)
from chat.core.persistence import (
    MongoSessionRepository,
    MongoMessageRepository,
    MongoSkillRepository,
    MongoModelRepository,
    MongoProviderRepository,
    RedisHotContext,
)
from chat.application.chat_turn_coordinator import ChatTurnCoordinator
from chat.application.tools.skill_tools.utils.skill_matcher import DefaultSkillMatcher
from chat.application.tools.skill_tools.utils.skill_cache_refresher import SkillCacheRefresher
from chat.application.tools.skill_tools import LoadSkillAssetTool
from chat.application.tools.skill_tools import LoadSkillTool
from chat.application.tools.core import ToolRegistry
from chat.application.tools.session_tools.search_history_tool import SearchHistoricalMessagesTool
from chat.core.config.nacos import nacos_client_manager
from chat.service_client import FileStorageClient, AIAssetClient, ResourceClient
from common.cloud.service_discovery import ServiceDiscovery
from common.http.rpc_client import RpcClient
from common.kafka import KafkaConsumerClient
from common.kafka.producer import KafkaProducerClient


async def _provide_nacos_naming() -> NacosNamingService:
    """延迟到首次 await，避免在 import 阶段触发 async Nacos 建连。"""
    return await nacos_client_manager.get_naming_client()


def _build_registry(tool_providers: List[providers.Provider]) -> ToolRegistry:
    """工厂函数：组装并返回已注册所有工具的 ToolRegistry 实例。"""
    registry = ToolRegistry()
    for provider in tool_providers:
        registry.register(provider)
    return registry


class Container(containers.DeclarativeContainer):
    """依赖注入容器，管理单例对象的生命周期。"""
    llm_provider = providers.Singleton(LiteLLMAdapter)
    memory_provider = providers.Singleton(Mem0Adapter)

    session_repo = providers.Singleton(MongoSessionRepository)
    message_repo = providers.Singleton(MongoMessageRepository)
    model_repo = providers.Singleton(MongoModelRepository)
    provider_repo = providers.Singleton(MongoProviderRepository)
    hot_context_repo = providers.Singleton(RedisHotContext)

    # 内部 RPC：Nacos 服务发现 + 通用 httpx 客户端 + file-storage typed facade
    service_discovery = providers.Singleton(
        ServiceDiscovery,
        naming_client_provider=providers.Object(_provide_nacos_naming),
        group_name=bootstrap_settings.NACOS_GROUP,
        default_strategy=settings.RPC_LB_STRATEGY,
        cache_ttl_seconds=settings.SERVICE_DISCOVERY_CACHE_TTL_SECONDS,
    )
    rpc_client = providers.Singleton(
        RpcClient,
        discovery=service_discovery,
        from_source_secret=settings.FROM_SOURCE_SECRET,
        timeout=settings.RPC_DEFAULT_TIMEOUT,
        retries=settings.RPC_DEFAULT_RETRIES,
        default_strategy=settings.RPC_LB_STRATEGY,
    )
    file_storage_client = providers.Singleton(
        FileStorageClient,
        rpc=rpc_client,
    )
    ai_asset_client = providers.Singleton(
        AIAssetClient,
        rpc=rpc_client,
    )
    resource_client = providers.Singleton(
        ResourceClient,
        rpc=rpc_client,
    )

    # Skill 子系统：
    # - SkillRepository 只读 Mongo 里的 Skill 实体
    # - SkillAssetLoader：DEV=True 用 LocalFS+OSS 回退；DEV=False 直连裸 OSS
    skill_repo = providers.Singleton(
        MongoSkillRepository,
        ai_asset_client=ai_asset_client
    )
    oss_skill_asset_loader = providers.Singleton(
        OssSkillAssetLoader,
        file_storage_client=file_storage_client,
        cache_dir=settings.SKILL_OSS_CACHE_DIR,
        cache_ttl_seconds=settings.SKILL_OSS_CACHE_TTL_SECONDS,
        gc_interval_seconds=settings.SKILL_OSS_CACHE_GC_INTERVAL_SECONDS,
    )
    # 开发态（profile=dev）使用 LocalFSSkillAssetLoader
    # 生产态（profile=prod）使用 OssSkillAssetLoader
    if bootstrap_settings.IS_DEV:
        skill_asset_loader = providers.Singleton(
            LocalFSSkillAssetLoader,
            root_dir=str(settings.SKILL_ASSETS_CACHE_PATH),
            oss_fallback=oss_skill_asset_loader,
        )
    else:
        skill_asset_loader = oss_skill_asset_loader
    # DefaultSkillMatcher
    skill_matcher = providers.Singleton(
        DefaultSkillMatcher,
        skill_repo=skill_repo,
    )
    # SkillCacheRefresher
    skill_cache_refresher = providers.Singleton(
        SkillCacheRefresher,
        matcher=skill_matcher,
        ttl_seconds=settings.SKILL_CACHE_TTL_SECONDS,
    )

    skill_published_consumer_handler = providers.Singleton(
        SkillPublishedConsumer,
        skill_repo=skill_repo,
        skill_cache_refresher=skill_cache_refresher,
    )

    skill_published_consumer = providers.Singleton(
        KafkaConsumerClient,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_SKILL_PUBLISHED_TOPIC,
        group_id=settings.KAFKA_SKILL_PUBLISHED_GROUP_ID,
        handler=skill_published_consumer_handler.provided.handle,
    )

    kafka_producer = providers.Singleton(
        KafkaProducerClient,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    )

    # 工具层：各 Tool 和 ToolRegistry 均为 Singleton，由容器统一管理生命周期
    # SearchHistoricalMessagesTool
    search_history_tool = providers.Singleton(
        SearchHistoricalMessagesTool,
        message_repo=message_repo,
    )
    # LoadSkillTool / LoadSkillAssetTool
    load_skill_tool = providers.Singleton(
        LoadSkillTool,
        skill_repo=skill_repo,
        resource_client=resource_client,
    )
    load_skill_asset_tool = providers.Singleton(
        LoadSkillAssetTool,
        skill_repo=skill_repo,
        resource_client=resource_client,
        skill_asset_loader=skill_asset_loader,
    )

    tool_providers = providers.List(
        search_history_tool,
        load_skill_tool,
        load_skill_asset_tool,
    )

    tool_registry = providers.Singleton(
        _build_registry,
        tool_providers=tool_providers,
    )

    # Application 层组件
    chat_turn_coordinator = providers.Factory(
        ChatTurnCoordinator,
        llm=llm_provider,
        memory=memory_provider,
        model_repo=model_repo,
        provider_repo=provider_repo,
        session_repo=session_repo,
        message_repo=message_repo,
        hot_context_repo=hot_context_repo,
        tool_registry=tool_registry,
        kafka_producer=kafka_producer,
        skill_matcher=skill_matcher,
    )


# 全局容器实例
container = Container()
