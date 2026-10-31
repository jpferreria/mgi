from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class Mem0StageSpec(BaseModel):
    recall_query: str = "architectural constraints, user preferences, past stage decisions"
    recall_top_k: int = 5
    auto_extract_on_complete: bool = True


class GraphifySeedQuery(BaseModel):
    type: Literal["community_summary", "query", "neighbors", "shortest_path"] = "community_summary"
    target: str = ""
    secondary_target: str = ""
    depth: int = 2


class GraphifyStageSpec(BaseModel):
    auto_refresh: bool = False
    seed_queries: list[GraphifySeedQuery] = Field(
        default_factory=lambda: [GraphifySeedQuery(type="community_summary")]
    )


class StageContract(BaseModel):
    """
    Represents Layer 3 of the ICM Five-Layer Context Hierarchy:
    A numbered stage contract (`0X_stage/CONTEXT.md`).
    """

    stage_id: str
    name: str
    stage_dir: Path
    contract_path: Path
    max_context_tokens: int = 6000
    hitl_checkpoint: bool = False
    mem0: Mem0StageSpec = Field(default_factory=Mem0StageSpec)
    graphify: GraphifyStageSpec = Field(default_factory=GraphifyStageSpec)
    tools: list[str] = Field(
        default_factory=lambda: [
            "graphify:query_graph",
            "graphify:get_neighbors",
            "mem0:search_memory",
            "mem0:add_memory",
            "fs:write_output",
        ]
    )
    inputs_section: str = ""
    process_section: str = ""
    outputs_section: str = ""
    quality_gates_section: str = ""
    raw_markdown_body: str = ""
    line_count: int = 0

    @property
    def input_paths(self) -> list[str]:
        """Extract backticked relative file paths declared in `## 1. Inputs`."""
        return self._extract_paths(self.inputs_section)

    @property
    def expected_output_paths(self) -> list[str]:
        """Extract backticked relative file paths declared in `## 3. Outputs`."""
        return [
            p
            for p in self._extract_paths(self.outputs_section)
            if p.startswith("output/") or "/" in p or p.endswith((".md", ".json", ".py", ".txt"))
        ]

    @property
    def quality_checklists(self) -> list[str]:
        """Extract `- [ ] ...` checklist items from `## 4. Quality Gates`."""
        items: list[str] = []
        for line in self.quality_gates_section.splitlines():
            m = re.match(r"^\s*[-*]\s*\[[ xX]?\]\s*(.+)$", line)
            if m:
                items.append(m.group(1).strip())
        return items

    @staticmethod
    def _extract_paths(section_text: str) -> list[str]:
        paths: list[str] = []
        for match in re.finditer(r"`([^`\n]+\.[a-zA-Z0-9]+)`", section_text):
            candidate = match.group(1).strip()
            if not candidate.startswith("http"):
                paths.append(candidate)
        return paths


class WorkspaceContract(BaseModel):
    """
    Represents Layer 2 of the ICM Five-Layer Context Hierarchy:
    The root `CONTEXT.md` routing map.
    """

    workspace_root: Path
    contract_path: Path
    project_name: str = "MGI Workspace"
    raw_content: str = ""
    stage_dirs: list[Path] = Field(default_factory=list)


class ICMParser:
    """
    Parses root and stage `CONTEXT.md` files according to the Interpretable Context Methodology
    (arXiv:2603.16021), supporting optional YAML frontmatter and structured Markdown sections.
    """

    STAGE_FOLDER_PATTERN = re.compile(r"^\d{2}_[a-zA-Z0-9_-]+$")

    @classmethod
    def parse_workspace(cls, workspace_root: Path) -> WorkspaceContract:
        root = workspace_root.resolve()
        contract_path = root / "CONTEXT.md"
        raw_content = (
            contract_path.read_text(encoding="utf-8") if contract_path.exists() else ""
        )

        title_match = re.search(r"^#\s+(.+)$", raw_content, flags=re.MULTILINE)
        project_name = title_match.group(1).strip() if title_match else root.name

        stage_dirs = sorted(
            [
                d
                for d in root.iterdir()
                if d.is_dir()
                and cls.STAGE_FOLDER_PATTERN.match(d.name)
                and (d / "CONTEXT.md").exists()
            ],
            key=lambda p: p.name,
        )

        return WorkspaceContract(
            workspace_root=root,
            contract_path=contract_path,
            project_name=project_name,
            raw_content=raw_content,
            stage_dirs=stage_dirs,
        )

    @classmethod
    def parse_stage(cls, stage_dir: Path) -> StageContract:
        stage_dir = stage_dir.resolve()
        contract_path = stage_dir / "CONTEXT.md"
        if not contract_path.exists():
            raise FileNotFoundError(f"Missing ICM Stage Contract at {contract_path}")

        raw_text = contract_path.read_text(encoding="utf-8")
        frontmatter, body = cls._split_frontmatter(raw_text)
        body_lines = [ln for ln in body.strip().splitlines() if ln.strip()]

        sections = cls._parse_markdown_sections(body)
        inputs_sec = cls._find_section(sections, ("1. inputs", "inputs"))
        process_sec = cls._find_section(sections, ("2. process", "process"))
        outputs_sec = cls._find_section(sections, ("3. outputs", "outputs"))
        gates_sec = cls._find_section(sections, ("4. quality gates", "quality gates", "checkpoints"))

        payload: dict[str, Any] = {
            "stage_id": frontmatter.get("stage_id", stage_dir.name),
            "name": frontmatter.get("name", stage_dir.name),
            "stage_dir": stage_dir,
            "contract_path": contract_path,
            "max_context_tokens": frontmatter.get("max_context_tokens", 6000),
            "hitl_checkpoint": frontmatter.get("hitl_checkpoint", False),
            "inputs_section": inputs_sec,
            "process_section": process_sec,
            "outputs_section": outputs_sec,
            "quality_gates_section": gates_sec,
            "raw_markdown_body": body.strip(),
            "line_count": len(body_lines),
        }
        if "mem0" in frontmatter and isinstance(frontmatter["mem0"], dict):
            payload["mem0"] = Mem0StageSpec.model_validate(frontmatter["mem0"])
        if "graphify" in frontmatter and isinstance(frontmatter["graphify"], dict):
            payload["graphify"] = GraphifyStageSpec.model_validate(frontmatter["graphify"])
        if "tools" in frontmatter and isinstance(frontmatter["tools"], list):
            payload["tools"] = [str(t) for t in frontmatter["tools"]]

        return StageContract.model_validate(payload)

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        if text.startswith("---\n"):
            parts = text.split("\n---\n", 1)
            if len(parts) == 2:
                raw_yaml = parts[0][4:]
                parsed = yaml.safe_load(raw_yaml) or {}
                if isinstance(parsed, dict):
                    return parsed, parts[1]
        return {}, text

    @staticmethod
    def _parse_markdown_sections(body: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current_header = "__preamble__"
        sections[current_header] = []

        for line in body.splitlines():
            m = re.match(r"^##\s+(.+)$", line.strip())
            if m:
                current_header = m.group(1).strip().lower()
                sections[current_header] = []
            else:
                sections[current_header].append(line)

        return {k: "\n".join(v).strip() for k, v in sections.items()}

    @staticmethod
    def _find_section(sections: dict[str, str],prefixes: tuple[str, ...]) -> str:
        for key, val in sections.items():
            for pref in prefixes:
                if key.startswith(pref) or pref in key:
                    return val
        return ""
