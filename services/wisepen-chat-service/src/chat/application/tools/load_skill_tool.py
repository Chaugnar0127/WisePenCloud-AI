from typing import Any, Dict

from common.logger import log_error

from chat.core.config.app_settings import settings
from chat.application.tools.core import (
    AllowedSkillIdCheck,
    ToolDefinition,
    ToolExecutionError,
    ToolLLMSpec,
    ToolParametersSchema,
    ToolPolicy,
    ToolRiskLevel,
)
from chat.domain.repositories import SkillRepository


class LoadSkillTool:
    """
    按 skill_id 懒加载 SKILL.md 正文 + assets manifest 摘要
    skill_id 必须在 tool_context['allowed_skill_ids']（本轮 matcher 命中的白名单）中，否则拒绝加载，防止 LLM 幻觉
    """

    def __init__(self, skill_repo: SkillRepository) -> None:
        self._skill_repo = skill_repo
        parameters_schema: Dict[str, Any] = {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "The slug id of the skill to load (e.g. 'paper-translation'). Must match one of the Available Skills.",
                },
            },
            "required": ["skill_id"],
        }
        self._definition = ToolDefinition(
            llm_spec=ToolLLMSpec(
                name="load_skill",
                description=(
                    "Lazy-load the full SKILL.md content and assets manifest for a given skill. "
                    "Only call this when the user's request is DIRECTLY covered by one of the Available Skills listed in the system context. "
                    "Do NOT call speculatively. After loading, strictly follow the instructions in SKILL.md; "
                    "call load_skill_asset to open a specific reference/template only if SKILL.md says you need it."
                ),
                parameters_schema=ToolParametersSchema(parameters_schema),
            ),
            policy=ToolPolicy(
                expose_by_default=False,
                persist_output=False,
                risk_level=ToolRiskLevel.MEDIUM,
                required_context_keys=("allowed_skill_ids",),
                timeout_seconds=5.0,
                max_output_chars=settings.TOOL_RESULT_MAX_CHARS,
            ),
            preflight_hooks=(AllowedSkillIdCheck(),),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, context: dict[str, Any], **kwargs: Any) -> str:
        skill_id = (kwargs.get("skill_id") or "").strip()
        if not skill_id:
            raise ToolExecutionError(
                reason="missing_skill_id",
                detail_reason="Missing required argument: skill_id.",
            )

        try:
            skill = await self._skill_repo.get_published_skill(skill_id)
        except Exception as e:
            log_error("load_skill 查询", e, skill_id=skill_id)
            raise ToolExecutionError(
                reason="skill_load_failed",
                detail_reason=f"Failed to load skill '{skill_id}': {type(e).__name__}",
                retryable=True,
                metadata={"detail": str(e), "skill_id": skill_id},
            ) from e

        if skill is None:
            raise ToolExecutionError(
                reason="skill_not_found",
                detail_reason=f"Skill '{skill_id}' not found.",
                metadata={"skill_id": skill_id},
            )

        # 拼接 header + SKILL.md + assets manifest 摘要
        lines = [
            f"[Loaded Skill] id={skill.skill_id} version={skill.version}",
            f"[Display Name] {skill.display_name}",
            "",
            "===== SKILL.md BEGIN =====",
            skill.skill_md.rstrip(),
            "===== SKILL.md END =====",
        ]

        if skill.assets_manifest:
            lines.append("")
            lines.append("[Assets Manifest] (use load_skill_asset to open any of these)")
            for asset in skill.assets_manifest:
                lines.append(
                    f"- path={asset.path} kind={asset.kind} size={asset.size_bytes} — {asset.description}"
                )

        return "\n".join(lines)
