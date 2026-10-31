from __future__ import annotations

import re
from pathlib import Path

from mem_graph_icm.memory.manager import Mem0LocalManager, MemoryRecord


class StageMemoryLifecycle:
    """
    Coordinates pre-stage memory recall (Layer 1 & Layer 4) and post-stage episodic/semantic
    memory consolidation into Mem0, automatically linking Graphify node references.
    """

    def __init__(self, manager: Mem0LocalManager) -> None:
        self.manager = manager

    def recall_for_stage(
        self,
        stage_id: str,
        recall_query: str,
        top_k: int = 5,
        graph_nodes: list[str] | None = None,
    ) -> list[MemoryRecord]:
        return self.manager.search_memories(
            query=recall_query,
            top_k=top_k,
            stage_id=stage_id,
            graph_nodes=graph_nodes,
        )

    def consolidate_stage_outputs(
        self,
        stage_id: str,
        output_files: list[Path],
        active_graph_nodes: list[str] | None = None,
        run_id: str | None = None,
    ) -> list[MemoryRecord]:
        """
        Extracts high-signal architectural decisions, findings, or takeaways from a completed
        ICM stage's `output/` files and commits them to Mem0 with `graph_nodes` metadata.
        """
        stored: list[MemoryRecord] = []
        for out_path in output_files:
            if not out_path.exists() or not out_path.is_file():
                continue
            try:
                content = out_path.read_text(encoding="utf-8")
            except Exception:
                continue

            # Extract bulleted decisions/takeaways or the first summary paragraph
            facts = self._extract_salient_facts(content, out_path.name)
            inferred_nodes = list(
                set((active_graph_nodes or []) + self._extract_code_refs(content))
            )

            for fact in facts[:5]:
                rec = self.manager.add_memory(
                    content=fact,
                    stage_id=stage_id,
                    graph_nodes=inferred_nodes[:10],
                    scope="project",
                    run_id=run_id,
                    extra_metadata={"source_artifact": out_path.name},
                )
                stored.append(rec)

        return stored

    def _extract_salient_facts(self, text: str, artifact_name: str) -> list[str]:
        facts: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")) and len(stripped) > 25:
                clean = stripped[2:].strip()
                facts.append(f"[{artifact_name}] {clean}")

        if not facts and text.strip():
            first_para = text.strip().split("\n\n")[0].replace("\n", " ").strip()
            if len(first_para) > 15:
                facts.append(f"[{artifact_name}] {first_para[:280]}")

        return facts

    def _extract_code_refs(self, text: str) -> list[str]:
        refs: list[str] = []
        for match in re.finditer(r"`([a-zA-Z0-9_./:-]+(?:\.py|::[a-zA-Z0-9_.]+))`", text):
            refs.append(match.group(1))
        return refs
