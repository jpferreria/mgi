from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from mem_graph_icm.config import MGIConfig
from mem_graph_icm.graph.indexer import GraphifyIndexer
from mem_graph_icm.graph.querier import GraphifyQuerier
from mem_graph_icm.icm.compiler import CompiledContext, ICMContextCompiler
from mem_graph_icm.icm.parser import ICMParser, StageContract, WorkspaceContract
from mem_graph_icm.icm.validator import ICMQualityValidator, ValidationReport
from mem_graph_icm.memory.lifecycle import StageMemoryLifecycle
from mem_graph_icm.memory.manager import Mem0LocalManager


class StageRunResult(BaseModel):
    stage_id: str
    status: str  # "completed", "paused_hitl", "failed"
    compiled_context: CompiledContext
    validation: ValidationReport
    agent_response: str = ""
    stored_memories_count: int = 0
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ICMPipelineRunner:
    """
    Executes an Interpretable Context Methodology (ICM) workspace sequentially across numbered
    folders (`01_discover` -> `02_plan` -> `03_execute` -> `04_verify`), coordinating:
      1. Graphify structural indexing / subgraph retrieval
      2. Mem0 pre-stage recall & post-stage episodic/semantic consolidation
      3. 5-Layer Context Compilation within strict token budgets
      4. Agent execution loop (or deterministic synthesis when running in dry-run/offline mode)
      5. Quality Gate verification & Human-in-the-Loop (HITL) checkpoints
    """

    def __init__(
        self,
        config: MGIConfig,
        agent_executor: Callable[[StageContract, CompiledContext, dict[str, Any]], str] | None = None,
        force_local_memory_fallback: bool = False,
    ) -> None:
        self.config = config
        self.indexer = GraphifyIndexer(config)
        self.querier = GraphifyQuerier(config)
        self.mem_manager = Mem0LocalManager(config, force_fallback=force_local_memory_fallback)
        self.mem_lifecycle = StageMemoryLifecycle(self.mem_manager)
        self.compiler = ICMContextCompiler(config, self.querier, self.mem_lifecycle)
        self.validator = ICMQualityValidator(config)
        self.agent_executor = agent_executor

    def run_pipeline(
        self,
        *,
        target_stage: str | None = None,
        template_vars: dict[str, Any] | None = None,
        auto_approve_hitl: bool = False,
        dry_run: bool = False,
    ) -> list[StageRunResult]:
        workspace = ICMParser.parse_workspace(self.config.workspace_root)
        if not workspace.stage_dirs:
            raise RuntimeError(
                f"No numbered ICM stage directories (`01_...`) found in {self.config.workspace_root}"
            )

        # Ensure Graphify index exists before running stages
        if not self.config.graphify.graph_json_path(self.config.workspace_root).exists():
            self.indexer.build_or_refresh()
        self.querier.load()

        run_id = str(uuid.uuid4())[:8]
        results: list[StageRunResult] = []

        for stage_dir in workspace.stage_dirs:
            stage = ICMParser.parse_stage(stage_dir)
            if target_stage and stage.stage_id != target_stage and stage_dir.name != target_stage:
                continue

            res = self.run_single_stage(
                workspace=workspace,
                stage=stage,
                run_id=run_id,
                template_vars=template_vars,
                auto_approve_hitl=auto_approve_hitl,
                dry_run=dry_run,
            )
            results.append(res)
            self._save_pipeline_state(run_id, results)

            if res.status in {"paused_hitl", "failed"}:
                break

        return results

    def run_single_stage(
        self,
        workspace: WorkspaceContract,
        stage: StageContract,
        *,
        run_id: str = "manual",
        template_vars: dict[str, Any] | None = None,
        auto_approve_hitl: bool = False,
        dry_run: bool = False,
    ) -> StageRunResult:
        started_at = datetime.now(timezone.utc).isoformat()

        if stage.graphify.auto_refresh:
            self.indexer.build_or_refresh()
            self.querier.load()

        # Step 1: Compile 5-Layer Context Window
        compiled = self.compiler.compile_stage_context(
            workspace=workspace,
            stage=stage,
            template_vars=template_vars,
        )

        # Step 2: Execute Stage Agent (custom executor, LiteLLM agent loop, or deterministic synthesizer)
        if dry_run:
            response_text = self._synthesize_deterministic_stage_output(stage, compiled)
        elif self.agent_executor is not None:
            response_text = self.agent_executor(stage, compiled, template_vars or {})
        else:
            from mem_graph_icm.agent.loop import StageAgentLoop

            loop = StageAgentLoop(
                config=self.config,
                querier=self.querier,
                mem_manager=self.mem_manager,
            )
            response_text = loop.execute(stage=stage, compiled=compiled, run_id=run_id)

        # Step 3: Validate Quality Gates & Output Deliverables
        validation = self.validator.validate_stage_outputs(stage)

        # Step 4: Consolidate Stage Findings into Mem0
        stored_count = 0
        if validation.passed and stage.mem0.auto_extract_on_complete:
            records = self.mem_lifecycle.consolidate_stage_outputs(
                stage_id=stage.stage_id,
                output_files=validation.created_outputs,
                active_graph_nodes=compiled.active_graph_nodes,
                run_id=run_id,
            )
            stored_count = len(records)

        if not validation.passed:
            status = "failed"
        elif stage.hitl_checkpoint and not auto_approve_hitl:
            status = "paused_hitl"
        else:
            status = "completed"

        return StageRunResult(
            stage_id=stage.stage_id,
            status=status,
            compiled_context=compiled,
            validation=validation,
            agent_response=response_text,
            stored_memories_count=stored_count,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _synthesize_deterministic_stage_output(
        self, stage: StageContract, compiled: CompiledContext
    ) -> str:
        """
        Deterministic fallback / dry-run compiler that materializes the stage's declared
        `output/` files using the compiled 5-Layer context (Graphify subgraphs + Mem0 memories).
        """
        out_paths = stage.expected_output_paths or [f"output/{stage.stage_id}_artifact.md"]
        written: list[str] = []

        for rel_out in out_paths:
            full_path = (stage.stage_dir / rel_out).resolve()
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if full_path.suffix == ".json":
                payload = {
                    "stage_id": stage.stage_id,
                    "name": stage.name,
                    "estimated_context_tokens": compiled.estimated_tokens,
                    "active_graph_nodes": compiled.active_graph_nodes,
                    "recalled_memory_ids": compiled.recalled_memory_ids,
                }
                full_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            else:
                body = [
                    f"# Deliverable: {stage.name} (`{stage.stage_id}`)",
                    "",
                    "## Context Summary",
                    f"- Compiled 5-Layer Tokens: `{compiled.estimated_tokens} / {compiled.max_tokens}`",
                    f"- Active Graphify Nodes: {', '.join(f'`{n}`' for n in compiled.active_graph_nodes[:8]) or 'root cluster'}",
                    f"- Recalled Mem0 Memories: `{len(compiled.recalled_memory_ids)}`",
                    "",
                    "## Key Findings & Decisions",
                    f"- Completed stage `{stage.stage_id}` adhering to ICM contract `{stage.contract_path.name}`.",
                    "- Validated structural dependencies against `graphify-out/graph.json`.",
                    "- Synchronized stage decisions with local Mem0 persistence.",
                ]
                full_path.write_text("\n".join(body) + "\n", encoding="utf-8")

            written.append(rel_out)

        return f"Materialized stage outputs: {', '.join(written)}"

    def _save_pipeline_state(self, run_id: str, results: list[StageRunResult]) -> None:
        state_path = (self.config.workspace_root / self.config.icm.state_file).resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": run_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "stages": [
                {
                    "stage_id": r.stage_id,
                    "status": r.status,
                    "estimated_tokens": r.compiled_context.estimated_tokens,
                    "max_tokens": r.compiled_context.max_tokens,
                    "outputs": [str(p.relative_to(self.config.workspace_root)) for p in r.validation.created_outputs if p.is_relative_to(self.config.workspace_root)],
                    "stored_memories_count": r.stored_memories_count,
                    "errors": r.validation.errors,
                }
                for r in results
            ],
        }
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
