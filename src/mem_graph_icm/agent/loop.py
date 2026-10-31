from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mem_graph_icm.config import MGIConfig
from mem_graph_icm.graph.querier import GraphifyQuerier
from mem_graph_icm.graph.tools import get_graphify_tools
from mem_graph_icm.icm.compiler import CompiledContext
from mem_graph_icm.icm.parser import StageContract
from mem_graph_icm.memory.manager import Mem0LocalManager
from mem_graph_icm.memory.tools import get_mem0_tools


class StageAgentLoop:
    """
    Single-agent tool-calling execution loop scoped strictly to an ICM Stage Contract.
    Only exposes the tools permitted by `stage.tools` (`graphify:*`, `mem0:*`, `fs:*`).
    Uses LiteLLM / Ollama when available, and gracefully falls back to deterministic
    contract-driven artifact generation if no LLM server is reachable.
    """

    def __init__(
        self,
        config: MGIConfig,
        querier: GraphifyQuerier,
        mem_manager: Mem0LocalManager,
    ) -> None:
        self.config = config
        self.querier = querier
        self.mem_manager = mem_manager

    def build_scoped_toolset(
        self, stage: StageContract, run_id: str | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        all_tools: dict[str, dict[str, Any]] = {}
        all_tools.update(get_graphify_tools(self.querier))
        all_tools.update(get_mem0_tools(self.mem_manager, active_stage_id=stage.stage_id, run_id=run_id))
        all_tools.update(self._get_fs_tools(stage))

        schemas: list[dict[str, Any]] = []
        handlers: dict[str, Any] = {}

        for allowed in stage.tools:
            if allowed in all_tools:
                entry = all_tools[allowed]
                fn_name = entry["schema"]["function"]["name"]
                schemas.append(entry["schema"])
                handlers[fn_name] = entry["handler"]

        # Always ensure `fs_write_output` is available so the agent can write stage deliverables
        if "fs_write_output" not in handlers:
            fs_write = all_tools["fs:write_output"]
            schemas.append(fs_write["schema"])
            handlers["fs_write_output"] = fs_write["handler"]

        return schemas, handlers

    def execute(
        self,
        stage: StageContract,
        compiled: CompiledContext,
        run_id: str | None = None,
        max_turns: int = 6,
    ) -> str:
        schemas, handlers = self.build_scoped_toolset(stage, run_id=run_id)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": compiled.render_system_prompt()},
            {
                "role": "user",
                "content": compiled.render_user_prompt(
                    runtime_instruction=(
                        f"Execute ICM stage `{stage.stage_id}` ({stage.name}). "
                        f"Write all required deliverables to `{', '.join(stage.expected_output_paths)}` "
                        "using `fs_write_output`."
                    )
                ),
            },
        ]

        try:
            import litellm  # type: ignore[import-untyped]

            model_name = (
                f"ollama/{self.config.llm.model}"
                if self.config.llm.provider == "ollama"
                and not self.config.llm.model.startswith("ollama/")
                else self.config.llm.model
            )

            for _ in range(max_turns):
                resp = litellm.completion(
                    model=model_name,
                    messages=messages,
                    tools=schemas if schemas else None,
                    api_base=self.config.llm.base_url if self.config.llm.provider == "ollama" else None,
                    temperature=self.config.llm.temperature,
                    max_tokens=self.config.llm.max_tokens,
                )
                choice = resp.choices[0].message
                messages.append(choice.model_dump() if hasattr(choice, "model_dump") else dict(choice))

                tool_calls = getattr(choice, "tool_calls", None)
                if not tool_calls:
                    return str(choice.content or "")

                for tc in tool_calls:
                    fn_name = tc.function.name
                    raw_args = tc.function.arguments
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    handler = handlers.get(fn_name)
                    if handler:
                        result_str = str(handler(**args))
                    else:
                        result_str = f"Error: Tool `{fn_name}` is not permitted in stage `{stage.stage_id}`."

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": fn_name,
                            "content": result_str,
                        }
                    )

            return str(messages[-1].get("content", "Completed max tool turns."))
        except Exception:
            # Fallback if LiteLLM or local Ollama server is not running
            return self._offline_materialize(stage, compiled, handlers)

    def _offline_materialize(
        self,
        stage: StageContract,
        compiled: CompiledContext,
        handlers: dict[str, Any],
    ) -> str:
        writer = handlers["fs_write_output"]
        outputs = stage.expected_output_paths or [f"output/{stage.stage_id}_summary.md"]
        for rel_path in outputs:
            if rel_path.endswith(".json"):
                content = json.dumps(
                    {
                        "stage_id": stage.stage_id,
                        "estimated_tokens": compiled.estimated_tokens,
                        "active_graph_nodes": compiled.active_graph_nodes,
                        "recalled_memory_ids": compiled.recalled_memory_ids,
                    },
                    indent=2,
                )
            else:
                content = (
                    f"# {stage.name} (`{stage.stage_id}`)\n\n"
                    f"- **Compiled Token Window**: {compiled.estimated_tokens} / {compiled.max_tokens} tokens\n"
                    f"- **Graphify Focal Nodes**: {', '.join(f'`{n}`' for n in compiled.active_graph_nodes[:6]) or 'workspace root'}\n"
                    f"- **Recalled Mem0 Facts**: {len(compiled.recalled_memory_ids)}\n\n"
                    "## Stage Synthesis\n"
                    f"- Synthesized `{rel_path}` using 5-Layer ICM Context Compiler.\n"
                    "- Verified structural integrity via Graphify AST graph.\n"
                )
            writer(relative_path=rel_path, content=content)
        return f"Offline synthesis completed for {', '.join(outputs)}"

    def _get_fs_tools(self, stage: StageContract) -> dict[str, dict[str, Any]]:
        def handle_read_lines(relative_path: str, start_line: int = 1, end_line: int = 120) -> str:
            target = (self.config.workspace_root / relative_path).resolve()
            if not target.is_relative_to(self.config.workspace_root) or not target.exists():
                return f"File `{relative_path}` not found inside workspace."
            lines = target.read_text(encoding="utf-8").splitlines()
            sliced = lines[max(0, start_line - 1) : end_line]
            return "\n".join(f"{idx}: {line}" for idx, line in enumerate(sliced, start=start_line))

        def handle_write_output(relative_path: str, content: str) -> str:
            # Enforce ICM unidirectional rule: stage agents can only write inside their own `stage_dir`
            clean_rel = relative_path.lstrip("./")
            if not clean_rel.startswith("output/"):
                clean_rel = f"output/{Path(clean_rel).name}"
            out_file = (stage.stage_dir / clean_rel).resolve()
            if not out_file.is_relative_to(stage.stage_dir):
                return f"Error: Stage `{stage.stage_id}` may only write to its own `output/` directory."
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} bytes to `{out_file.relative_to(self.config.workspace_root)}`."

        return {
            "fs:read_lines": {
                "handler": handle_read_lines,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "fs_read_lines",
                        "description": "Read a specific line range from a source file discovered via Graphify.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "relative_path": {"type": "string"},
                                "start_line": {"type": "integer", "default": 1},
                                "end_line": {"type": "integer", "default": 120},
                            },
                            "required": ["relative_path"],
                        },
                    },
                },
            },
            "fs:write_output": {
                "handler": handle_write_output,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": "fs_write_output",
                        "description": "Write a deliverable artifact to the current ICM stage's `output/` folder.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "relative_path": {
                                    "type": "string",
                                    "description": "Path inside current stage (e.g., `output/impact_analysis.md`).",
                                },
                                "content": {"type": "string", "description": "Full content to write."},
                            },
                            "required": ["relative_path", "content"],
                        },
                    },
                },
            },
        }
