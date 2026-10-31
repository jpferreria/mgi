from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mem_graph_icm.config import MGIConfig
from mem_graph_icm.graph.querier import GraphifyQuerier
from mem_graph_icm.icm.parser import StageContract, WorkspaceContract
from mem_graph_icm.memory.lifecycle import StageMemoryLifecycle


class CompiledContext(BaseModel):
    """
    The assembled 5-Layer ICM context window for a single stage execution,
    guaranteed to obey `max_context_tokens`.
    """

    stage_id: str
    layer1_identity: str
    layer2_routing: str
    layer3_stage_contract: str
    layer4_reference_material: str
    layer5_working_artifacts: str
    estimated_tokens: int
    max_tokens: int
    pruned_layers: list[str] = Field(default_factory=list)
    active_graph_nodes: list[str] = Field(default_factory=list)
    recalled_memory_ids: list[str] = Field(default_factory=list)

    def render_system_prompt(self) -> str:
        return "\n\n---\n\n".join(
            [
                "<!-- ICM LAYER 1: IDENTITY & GLOBAL PREFERENCES -->\n" + self.layer1_identity,
                "<!-- ICM LAYER 2: WORKSPACE ROUTING -->\n" + self.layer2_routing,
                "<!-- ICM LAYER 3: STAGE CONTRACT -->\n" + self.layer3_stage_contract,
            ]
        )

    def render_user_prompt(self, runtime_instruction: str = "") -> str:
        blocks = [
            "<!-- ICM LAYER 4: REFERENCE MATERIAL (GRAPHIFY + MEM0) -->\n"
            + self.layer4_reference_material,
            "<!-- ICM LAYER 5: UPSTREAM WORKING ARTIFACTS -->\n" + self.layer5_working_artifacts,
        ]
        if runtime_instruction:
            blocks.append(f"## Immediate Execution Instruction\n{runtime_instruction}")
        return "\n\n---\n\n".join(blocks)


class ICMContextCompiler:
    """
    Implements the Five-Layer Context Hierarchy (arXiv:2603.16021):
      - Layer 1: Identity (`_config/IDENTITY.md` + Global Mem0 Profile)
      - Layer 2: Routing (`./CONTEXT.md`)
      - Layer 3: Stage Contract (`./0X_stage/CONTEXT.md`)
      - Layer 4: Reference Material (Graphify Subgraphs + Mem0 Stage Recall)
      - Layer 5: Working Artifacts (Explicit upstream files declared in `## 1. Inputs`)

    Enforces strict token discipline (default 2,000–8,000 tokens) by dynamically trimming
    Layer 4 and Layer 5 if the combined context approaches `stage.max_context_tokens`.
    """

    def __init__(
        self,
        config: MGIConfig,
        graph_querier: GraphifyQuerier,
        memory_lifecycle: StageMemoryLifecycle,
    ) -> None:
        self.config = config
        self.graph_querier = graph_querier
        self.memory_lifecycle = memory_lifecycle

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // self.config.icm.chars_per_token)

    def compile_stage_context(
        self,
        workspace: WorkspaceContract,
        stage: StageContract,
        template_vars: dict[str, Any] | None = None,
    ) -> CompiledContext:
        vars_map = template_vars or {}
        max_tokens = stage.max_context_tokens or self.config.icm.default_max_context_tokens

        # Layer 1: Identity + Global Mem0 Preferences
        layer1 = self._build_layer1_identity(workspace.workspace_root)

        # Layer 2: Root Routing Map
        layer2 = workspace.raw_content.strip() or f"# Workspace: {workspace.project_name}"

        # Layer 3: Stage Contract
        layer3 = stage.raw_markdown_body

        # Layer 4: Graphify Structural Subgraphs + Mem0 Stage Recall
        layer4, graph_nodes, mem_ids = self._build_layer4_reference(stage, vars_map)

        # Layer 5: Upstream Working Artifacts
        layer5 = self._build_layer5_artifacts(stage)

        # Budget Enforcement: Layers 1, 2, 3 are core architectural contracts.
        # If total exceeds `max_tokens`, prune Layer 4 first, then Layer 5, then Layer 2, then Layer 1.
        pruned: list[str] = []
        core_tokens = (
            self.estimate_tokens(layer1)
            + self.estimate_tokens(layer2)
            + self.estimate_tokens(layer3)
        )
        remaining_budget = max(0, max_tokens - core_tokens)

        l4_tokens = self.estimate_tokens(layer4)
        l5_tokens = self.estimate_tokens(layer5)

        if l4_tokens + l5_tokens > remaining_budget:
            l4_cap = max(25, int(remaining_budget * 0.45))
            if l4_tokens > l4_cap:
                layer4 = self._truncate_to_tokens(layer4, l4_cap)
                pruned.append("layer4_reference_material")
                l4_tokens = self.estimate_tokens(layer4)

            l5_cap = max(25, remaining_budget - l4_tokens)
            if l5_tokens > l5_cap:
                layer5 = self._truncate_to_tokens(layer5, l5_cap)
                pruned.append("layer5_working_artifacts")

        # Progressive core-layer trimming if `max_tokens` is unusually small
        for layer_name in ("layer2_routing", "layer1_identity", "layer3_stage_contract"):
            total_tokens = (
                self.estimate_tokens(layer1)
                + self.estimate_tokens(layer2)
                + self.estimate_tokens(layer3)
                + self.estimate_tokens(layer4)
                + self.estimate_tokens(layer5)
            )
            if total_tokens <= max_tokens:
                break
            excess = total_tokens - max_tokens
            if layer_name == "layer2_routing":
                target_tok = max(20, self.estimate_tokens(layer2) - excess)
                layer2 = self._truncate_to_tokens(layer2, target_tok)
            elif layer_name == "layer1_identity":
                target_tok = max(20, self.estimate_tokens(layer1) - excess)
                layer1 = self._truncate_to_tokens(layer1, target_tok)
            elif layer_name == "layer3_stage_contract":
                target_tok = max(20, self.estimate_tokens(layer3) - excess)
                layer3 = self._truncate_to_tokens(layer3, target_tok)
            if layer_name not in pruned:
                pruned.append(layer_name)

        total_tokens = (
            self.estimate_tokens(layer1)
            + self.estimate_tokens(layer2)
            + self.estimate_tokens(layer3)
            + self.estimate_tokens(layer4)
            + self.estimate_tokens(layer5)
        )

        return CompiledContext(
            stage_id=stage.stage_id,
            layer1_identity=layer1,
            layer2_routing=layer2,
            layer3_stage_contract=layer3,
            layer4_reference_material=layer4,
            layer5_working_artifacts=layer5,
            estimated_tokens=total_tokens,
            max_tokens=max_tokens,
            pruned_layers=pruned,
            active_graph_nodes=graph_nodes,
            recalled_memory_ids=mem_ids,
        )

    def _build_layer1_identity(self, workspace_root: Path) -> str:
        identity_path = workspace_root / "_config" / "IDENTITY.md"
        constraints_path = workspace_root / "_config" / "CONSTRAINTS.md"

        blocks: list[str] = []
        if identity_path.exists():
            blocks.append(identity_path.read_text(encoding="utf-8").strip())
        else:
            blocks.append(
                "# Agent Identity\nYou are an autonomous ICM Stage Compiler Agent operating with strict context discipline."
            )

        if constraints_path.exists():
            blocks.append(constraints_path.read_text(encoding="utf-8").strip())

        global_memories = self.memory_lifecycle.manager.search_memories(
            query="user preference, global constraint, coding standard",
            top_k=3,
            scope="global",
        )
        if global_memories:
            mem_lines = ["## Persistent Global Preferences (Mem0)"]
            for m in global_memories:
                mem_lines.append(f"- {m.memory}")
            blocks.append("\n".join(mem_lines))

        return "\n\n".join(blocks)

    def _build_layer4_reference(
        self, stage: StageContract, vars_map: dict[str, Any]
    ) -> tuple[str, list[str], list[str]]:
        sections: list[str] = []
        active_nodes: list[str] = []

        # 1. Execute Graphify Seed Queries
        for sq in stage.graphify.seed_queries:
            target = self._interpolate(sq.target, vars_map)
            if sq.type == "community_summary":
                sections.append("## Graphify Architectural Overview\n" + self.graph_querier.community_summary())
            elif sq.type == "query" and target:
                sub = self.graph_querier.query_graph(target)
                active_nodes.extend(n.id for n in sub.nodes)
                sections.append(sub.to_markdown_summary())
            elif sq.type == "neighbors" and target:
                sub = self.graph_querier.get_neighbors(target, depth=sq.depth)
                active_nodes.extend(n.id for n in sub.nodes)
                sections.append(sub.to_markdown_summary())
            elif sq.type == "shortest_path" and target and sq.secondary_target:
                sec = self._interpolate(sq.secondary_target, vars_map)
                edges = self.graph_querier.shortest_path(target, sec)
                if edges:
                    lines = [f"### Shortest Path (`{target}` -> `{sec}`)"]
                    lines.extend(f"- `{e.source}` --[{e.relation}]--> `{e.target}`" for e in edges)
                    sections.append("\n".join(lines))

        # 2. Execute Mem0 Stage Recall anchored to discovered Graphify nodes
        recall_query = self._interpolate(stage.mem0.recall_query, vars_map)
        memories = self.memory_lifecycle.recall_for_stage(
            stage_id=stage.stage_id,
            recall_query=recall_query,
            top_k=stage.mem0.recall_top_k,
            graph_nodes=active_nodes,
        )
        mem_ids = [m.id for m in memories]
        if memories:
            mem_lines = [f"## Recalled Episodic & Semantic Memories (Mem0, query=`{recall_query}`)"]
            for m in memories:
                src_stage = m.metadata.get("stage_id", "global")
                anchors = m.metadata.get("graph_nodes", [])
                anchor_tag = f" [nodes: {', '.join(anchors[:3])}]" if anchors else ""
                mem_lines.append(f"- **[{src_stage}]** {m.memory}{anchor_tag}")
            sections.append("\n".join(mem_lines))
        else:
            sections.append("## Recalled Memories (Mem0)\n*No prior memories matched this stage query.*")

        return "\n\n".join(sections), list(dict.fromkeys(active_nodes)), mem_ids

    def _build_layer5_artifacts(self, stage: StageContract) -> str:
        blocks: list[str] = []
        for rel_path in stage.input_paths:
            # Skip GRAPH_REPORT.md if already injected in Layer 4
            if rel_path.endswith("GRAPH_REPORT.md"):
                continue
            resolved = (stage.stage_dir / rel_path).resolve()
            if not resolved.exists():
                # Also try resolving relative to workspace root
                alt = (self.config.workspace_root / rel_path).resolve()
                if alt.exists():
                    resolved = alt

            if resolved.exists() and resolved.is_file():
                try:
                    content = resolved.read_text(encoding="utf-8").strip()
                    blocks.append(f"### Input Artifact: `{rel_path}`\n```markdown\n{content}\n```")
                except Exception:
                    blocks.append(f"### Input Artifact: `{rel_path}` (Unreadable binary/encoding)")
            else:
                blocks.append(f"### Input Artifact: `{rel_path}` *(Not yet created)*")

        if not blocks:
            return "*No upstream input artifacts declared for this stage.*"
        return "\n\n".join(blocks)

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        max_chars = max(60, max_tokens * self.config.icm.chars_per_token)
        if len(text) <= max_chars:
            return text
        marker = "\n\n...[TRUNCATED BY ICM CONTEXT COMPILER FOR TOKEN DISCIPLINE]..."
        keep = max(20, max_chars - len(marker))
        return text[:keep] + marker

    @staticmethod
    def _interpolate(template: str, vars_map: dict[str, Any]) -> str:
        res = template
        for k, v in vars_map.items():
            res = res.replace(f"{{{{{k}}}}}", str(v))
            res = res.replace(f"{{{{input.{k}}}}}", str(v))
        return res
