from __future__ import annotations

from typing import Any

from mem_graph_icm.memory.manager import Mem0LocalManager


def get_mem0_tools(
    manager: Mem0LocalManager,
    active_stage_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Returns standard OpenAI/LiteLLM tool schemas and callable handlers for Mem0
    (`mem0:search_memory` and `mem0:add_memory`).
    """

    def handle_search_memory(query: str, top_k: int = 5) -> str:
        records = manager.search_memories(
            query=query,
            top_k=top_k,
            stage_id=active_stage_id,
        )
        if not records:
            return f"No persistent memories found matching `{query}`."
        lines = [f"Found {len(records)} Mem0 memories for `{query}`:"]
        for r in records:
            stage = r.metadata.get("stage_id", "global")
            nodes = r.metadata.get("graph_nodes", [])
            anchor_str = f" (Graphify anchors: {', '.join(nodes)})" if nodes else ""
            lines.append(f"- [{stage}] {r.memory}{anchor_str}")
        return "\n".join(lines)

    def handle_add_memory(
        content: str,
        graph_nodes: list[str] | None = None,
        scope: str = "project",
    ) -> str:
        rec = manager.add_memory(
            content=content,
            stage_id=active_stage_id,
            graph_nodes=graph_nodes or [],
            scope=scope,
            run_id=run_id,
        )
        return f"Saved memory `{rec.id}` (stage={active_stage_id or 'global'}, scope={scope})."

    return {
        "mem0:search_memory": {
            "handler": handle_search_memory,
            "schema": {
                "type": "function",
                "function": {
                    "name": "mem0_search_memory",
                    "description": "Search persistent Mem0 episodic and semantic memories across sessions and ICM stages.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Natural language search query."},
                            "top_k": {"type": "integer", "default": 5},
                        },
                        "required": ["query"],
                    },
                },
            },
        },
        "mem0:add_memory": {
            "handler": handle_add_memory,
            "schema": {
                "type": "function",
                "function": {
                    "name": "mem0_add_memory",
                    "description": "Store an important architectural decision, bug fix, or user preference into Mem0.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Fact or decision to remember."},
                            "graph_nodes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional Graphify node IDs anchored to this memory.",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["global", "project", "stage"],
                                "default": "project",
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
        },
    }
