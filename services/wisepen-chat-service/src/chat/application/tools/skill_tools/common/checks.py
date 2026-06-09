from typing import Any

from chat.application.tools.core.definition import ToolParametersSchema, ToolPolicy
from chat.application.tools.core.execution.hooks.base import ToolPreflightHook, ToolPreflightResult
from chat.application.tools.core.llm.invocation import ToolInvocation


class AllowedSkillIdCheck(ToolPreflightHook):
    name = "allowed_skill_id"

    async def check(
        self,
        invocation: ToolInvocation,
        policy: ToolPolicy,
        parameters_schema: ToolParametersSchema,
        context: dict[str, Any],
    ) -> ToolPreflightResult:
        skill_id = invocation.tool_call_arguments.get("skill_id")
        allowed_skill_ids = context.get("allowed_skill_ids") or []

        if not isinstance(skill_id, str) or not skill_id.strip():
            return ToolPreflightResult(ok=False, message="Missing required tool argument: skill_id")

        if skill_id not in allowed_skill_ids:
            return ToolPreflightResult(
                ok=False,
                message=f"Skill '{skill_id}' is not allowed in this turn.",
            )

        return ToolPreflightResult(ok=True)
