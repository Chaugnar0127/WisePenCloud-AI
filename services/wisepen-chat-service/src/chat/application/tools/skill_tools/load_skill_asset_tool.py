from typing import Any, Dict

from common.logger import log_error, log_fail

from chat.core.config.app_settings import settings
from chat.application.tools.core import (
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.application.tools.skill_tools.common import AllowedSkillIdCheck, build_skill_asset_output_placeholder
from chat.domain.interfaces.skill_asset_loader import SkillAssetLoader
from chat.domain.repositories import SkillRepository


class LoadSkillAssetTool:
    """
    按 skill_id + 相对路径懒加载 Skill Bundle 内的某个资产（reference / template / 示例等）
    skill_id 必须在 tool_context['allowed_skill_ids']（本轮 matcher 命中的白名单）中，否则拒绝加载，防止 LLM 幻觉
    该 path 必须出现在 Skill.assets_manifest 中（白名单），否则拒绝加载，防止 LLM 幻觉导致越权访问
    """

    def __init__(
        self,
        skill_repo: SkillRepository,
        skill_asset_loader: SkillAssetLoader,
    ) -> None:
        self._skill_repo = skill_repo
        self._skill_asset_loader = skill_asset_loader
        parameters_schema: Dict[str, Any] = {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "The slug id of the skill; must match an Available Skill.",
                },
                "path": {
                    "type": "string",
                    "description": "Relative POSIX path of the asset, exactly as listed in the skill's assets manifest (e.g. 'references/citation-styles.md').",
                },
            },
            "required": ["skill_id", "path"],
        }
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="load_skill_asset",
                description=(
                    "Lazy-load the content of a specific asset (reference, template, example, etc.) "
                    "belonging to a skill that has already been loaded via load_skill. "
                    "You must pass a path that appears in the skill's assets manifest; "
                    "do NOT invent paths. Only call when SKILL.md explicitly tells you to consult that asset."
                ),
                parameters_schema=ToolParametersSchema(parameters_schema),
            ),
            policy=ToolPolicy(
                expose_by_default=False,
                persist_output=False,
                persisted_output_placeholder_factory=build_skill_asset_output_placeholder,
                risk_level=ToolRiskLevel.MEDIUM,
                required_context_keys=("allowed_skill_ids",),
                timeout_seconds=8.0,
                max_output_chars=settings.TOOL_RESULT_MAX_CHARS,
            ),
            preflight_hooks=(AllowedSkillIdCheck(),),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        skill_id = (kwargs.get("skill_id") or "").strip()
        path = (kwargs.get("path") or "").strip()
        if not skill_id or not path:
            raise ToolExecutionError(
                reason="missing_skill_asset_input",
                detail_reason="Missing required arguments: skill_id, path.",
            )

        try:
            skill = await self._skill_repo.get_published_skill(skill_id)
        except Exception as e:
            log_error("load_skill_asset 查询", e, skill_id=skill_id, path=path)
            raise ToolExecutionError(
                reason="skill_query_failed",
                detail_reason=f"Failed to query skill '{skill_id}': {type(e).__name__}",
                retryable=True,
                metadata={"detail": str(e), "skill_id": skill_id, "path": path},
            ) from e
        if skill is None:
            raise ToolExecutionError(
                reason="skill_not_found",
                detail_reason=f"Skill '{skill_id}' not found.",
                metadata={"skill_id": skill_id},
            )

        # Manifest 白名单校验：path 必须是 publish 时冻结在 assets_manifest 里的那些
        path_to_object_key = {asset.path: asset.object_key for asset in skill.assets_manifest}
        if path not in path_to_object_key:
            log_fail(
                "load_skill_asset path 校验",
                "path 不在 assets_manifest 中",
                skill_id=skill_id,
                path=path,
            )
            raise ToolExecutionError(
                reason="asset_path_not_declared",
                detail_reason=f"Asset path '{path}' is not declared in the assets manifest of skill '{skill_id}'.",
                metadata={
                    "skill_id": skill_id,
                    "path": path,
                    "available": sorted(path_to_object_key.keys()),
                },
            )
        object_key = path_to_object_key[path]
        if not object_key:
            # 发布侧理论上必填 object_key，出现空值说明数据异常，走降级
            log_fail(
                "load_skill_asset object_key 缺失",
                "assets_manifest 条目 object_key 为空",
                skill_id=skill_id,
                path=path,
            )
            raise ToolExecutionError(
                reason="asset_object_key_missing",
                detail_reason=f"Asset '{path}' of skill '{skill_id}' has no object_key registered.",
                metadata={"skill_id": skill_id, "path": path},
            )

        try:
            raw = await self._skill_asset_loader.load_by_object_key(object_key)
        except Exception as e:
            log_error(
                "load_skill_asset 读取",
                e,
                skill_id=skill_id,
                version=skill.version,
                path=path,
                object_key=object_key,
            )
            raise ToolExecutionError(
                reason="asset_read_failed",
                detail_reason=f"Failed to read asset: {type(e).__name__}",
                retryable=True,
                metadata={"skill_id": skill_id, "path": path, "object_key": object_key, "detail": str(e)},
            ) from e

        # Loader 返回 bytes：资产可能是文本（.md / .py / .json）也可能是二进制（.png / .pdf / .wasm ...）
        # 在给 LLM 的边界上做 UTF-8 严格解码，拒绝不可文本化的二进制资产
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            log_fail(
                "load_skill_asset 解码",
                "资产非 UTF-8 文本，无法直接返回给 LLM",
                skill_id=skill_id,
                version=skill.version,
                path=path,
                object_key=object_key,
                bytes=len(raw),
            )
            raise ToolExecutionError(
                reason="asset_not_text",
                detail_reason=(
                    f"Asset '{path}' of skill '{skill_id}' appears to be a binary blob "
                    f"({len(raw)} bytes) and cannot be shown as text."
                ),
                metadata={"skill_id": skill_id, "path": path, "bytes": len(raw)},
            )

        # 字符截断，防止超长资产撑爆上下文水位
        if len(content) > settings.TOOL_RESULT_MAX_CHARS:
            content = content[: settings.TOOL_RESULT_MAX_CHARS] + "\n...[truncated]"

        return (
            f"[Loaded Asset] skill_id={skill_id} version={skill.version} path={path}\n"
            f"===== ASSET BEGIN =====\n"
            f"{content}\n"
            f"===== ASSET END ====="
        )
