import os
from pathlib import Path
from src.context_extractor import ProjectContext


IDE_FORMATS = {
    "kilocode": {
        "filename": ".kilocoderules",
        "format": "markdown",
    },
    "cursor": {
        "filename": ".cursorrules",
        "format": "markdown",
    },
    "cline": {
        "filename": ".clinerules",
        "format": "markdown",
    },
    "windsurf": {
        "filename": ".windsurfrules",
        "format": "markdown",
    },
    "copilot": {
        "filename": ".github/copilot-instructions.md",
        "format": "markdown",
    },
    "antigravity": {
        "filename": ".antigravityrules",
        "format": "markdown",
    },
}


def export_to_ide(
    project_path: str,
    context: ProjectContext | None,
    agent_prompts: dict[str, str],
    ide_keys: list[str],
) -> list[str]:
    generated = []
    root = Path(project_path)

    if context is None:
        context = ProjectContext(project_name="Project")

    for ide_key in ide_keys:
        if ide_key not in IDE_FORMATS:
            continue

        ide = IDE_FORMATS[ide_key]
        content = _build_rule_file(context, agent_prompts, ide_key)

        filepath = root / ide["filename"]
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

        generated.append(ide["filename"])

    return generated


def _build_rule_file(
    context: ProjectContext,
    agent_prompts: dict[str, str],
    ide_key: str,
) -> str:
    lines = []

    lines.append(f"# AI CTO Agents — {context.project_name}")
    lines.append("")
    lines.append("This project has 8 specialized AI CTO agents. Use them based on the task type.")
    lines.append("")

    lines.append("## Project Context")
    lines.append("")
    for line in context.raw_context.splitlines():
        lines.append(line)
    lines.append("")

    lines.append("## Agent Workflow Pipeline")
    lines.append("")
    lines.append("1. **CTO Orchestrator** — First point of contact. Coordinates which agents to use.")
    lines.append("2. **Audit Analyzer** — When reviewing audits, security scans, or performance reports.")
    lines.append("3. **Architect** — When designing or reviewing system architecture and APIs.")
    lines.append("4. **Planner** — When creating implementation plans or breaking down tasks.")
    lines.append("5. **Executor** — When writing, refactoring, or fixing code.")
    lines.append("6. **Tester** — When writing tests or reviewing code quality.")
    lines.append("7. **Monitor** — When tracking progress or identifying bottlenecks.")
    lines.append("8. **Documenter** — When generating documentation, READMEs, or API docs.")
    lines.append("")

    lines.append("## Agent Definitions")
    lines.append("")

    agent_display = {
        "cto_orchestrator": "CTO Orchestrator",
        "cto_audit_analyzer": "Audit Analyzer",
        "cto_architect": "Architect",
        "cto_planner": "Planner",
        "cto_executor": "Executor",
        "cto_tester": "Tester",
        "cto_monitor": "Monitor",
        "cto_documenter": "Documenter",
    }

    for agent_key, display_name in agent_display.items():
        prompt = agent_prompts.get(agent_key, "")
        lines.append(f"### {display_name}")
        lines.append("")
        lines.append(prompt)
        lines.append("")

    lines.append("## Coding Standards")
    lines.append("")
    lines.append("- Follow the project's existing code style and conventions")
    lines.append("- Reference actual file paths when creating or modifying files")
    lines.append("- Use the project's established patterns before introducing new ones")
    lines.append("- Always run linting and tests before declaring a task complete")
    lines.append("")

    return "\n".join(lines)
