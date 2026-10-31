from __future__ import annotations

from pathlib import Path
from typing import Any

from mem_graph_icm.config import MGIConfig, get_config
from mem_graph_icm.graph.indexer import GraphifyIndexer
from mem_graph_icm.graph.querier import GraphifyQuerier
from mem_graph_icm.icm.compiler import ICMContextCompiler
from mem_graph_icm.icm.parser import ICMParser
from mem_graph_icm.memory.lifecycle import StageMemoryLifecycle
from mem_graph_icm.memory.manager import Mem0LocalManager


class MGIMCPToolset:
    """
    Core MCP tool handlers exposing the unified `mem-graph-icm` stack to external coding agents
    (Antigravity, Claude Code, Cursor, etc.). Can be used directly in Python or wrapped by
    `mcp.server.fastmcp.FastMCP`.
    """

    def __init__(self, config: MGIConfig | None = None) -> None:
        self.config = config or get_config()
        self.indexer = GraphifyIndexer(self.config)
        self.querier = GraphifyQuerier(self.config)
        self.mem_manager = Mem0LocalManager(self.config)
        self.mem_lifecycle = StageMemoryLifecycle(self.mem_manager)
        self.compiler = ICMContextCompiler(self.config, self.querier, self.mem_lifecycle)

    def icm_compile_stage(self, stage_id: str, focal_symbol: str = "") -> dict[str, Any]:
        """Compile the 5-Layer ICM prompt for a specific numbered stage."""
        workspace = ICMParser.parse_workspace(self.config.workspace_root)
        target_dir = self.config.workspace_root / stage_id
        stage = ICMParser.parse_stage(target_dir)
        compiled = self.compiler.compile_stage_context(
            workspace=workspace,
            stage=stage,
            template_vars={"focal_symbol": focal_symbol} if focal_symbol else {},
        )
        return {
            "stage_id": compiled.stage_id,
            "estimated_tokens": compiled.estimated_tokens,
            "max_tokens": compiled.max_tokens,
            "pruned_layers": compiled.pruned_layers,
            "system_prompt": compiled.render_system_prompt(),
            "user_prompt": compiled.render_user_prompt(),
        }

    def graphify_query(self, query: str, depth: int = 2) -> str:
        """Query the Graphify AST/knowledge graph and return a low-token neighborhood summary."""
        if not self.querier.ensure_loaded():
            self.indexer.build_or_refresh()
            self.querier.load()
        sub = self.querier.get_neighbors(query, depth=depth)
        if not sub.nodes:
            sub = self.querier.query_graph(query)
        return sub.to_markdown_summary()

    def mem0_recall(self, query: str, stage_id: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        """Search persistent Mem0 memories anchored to ICM stages and Graphify nodes."""
        recs = self.mem_manager.search_memories(query=query, stage_id=stage_id, top_k=top_k)
        return [r.model_dump() for r in recs]

    def mem0_remember(
        self,
        content: str,
        stage_id: str = "global",
        graph_nodes: list[str] | None = None,
        scope: str = "project",
    ) -> dict[str, Any]:
        """Save a new architectural decision, bug resolution, or preference to Mem0."""
        rec = self.mem_manager.add_memory(
            content=content,
            stage_id=stage_id,
            graph_nodes=graph_nodes,
            scope=scope,
        )
        return rec.model_dump()


def create_mcp_server(workspace_root: Path | str | None = None) -> Any:
    """
    Creates an MCP server instance (via `mcp.server.fastmcp.FastMCP` if installed, or returns
    the `MGIMCPToolset` adapter).
    """
    cfg = get_config(workspace_root)
    toolset = MGIMCPToolset(cfg)

    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

        mcp = FastMCP("mem-graph-icm")

        @mcp.tool()
        def icm_compile_stage(stage_id: str, focal_symbol: str = "") -> dict[str, Any]:
            """Compile the 5-Layer ICM context window for a stage (`01_discover`, etc.)."""
            return toolset.icm_compile_stage(stage_id=stage_id, focal_symbol=focal_symbol)

        @mcp.tool()
        def graphify_query(query: str, depth: int = 2) -> str:
            """Query the Graphify structural knowledge graph around a symbol or file."""
            return toolset.graphify_query(query=query, depth=depth)

        @mcp.tool()
        def mem0_recall(query: str, stage_id: str = "", top_k: int = 5) -> list[dict[str, Any]]:
            """Recall persistent episodic/semantic memories from Mem0."""
            return toolset.mem0_recall(query=query, stage_id=stage_id or None, top_k=top_k)

        @mcp.tool()
        def mem0_remember(
            content: str,
            stage_id: str = "global",
            graph_nodes: list[str] | None = None,
            scope: str = "project",
        ) -> dict[str, Any]:
            """Store a persistent fact or decision in Mem0 anchored to Graphify nodes."""
            return toolset.mem0_remember(
                content=content,
                stage_id=stage_id,
                graph_nodes=graph_nodes,
                scope=scope,
            )

        return mcp
    except ImportError:
        return toolset
