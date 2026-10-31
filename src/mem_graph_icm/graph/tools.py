from __future__ import annotations

from typing import Any, Callable

from mem_graph_icm.graph.querier import GraphifyQuerier


def get_graphify_tools(querier: GraphifyQuerier) -> dict[str, dict[str, Any]]:
    """
    Returns standard OpenAI/LiteLLM tool schemas and callable handlers for Graphify
    so ICM stages can selectively enable `graphify:query_graph`, `graphify:get_neighbors`,
    or `graphify:shortest_path`.
    """

    def handle_query_graph(query: str, limit: int = 15) -> str:
        res = querier.query_graph(query=query, limit=limit)
        return res.to_markdown_summary(max_nodes=limit)

    def handle_get_neighbors(target: str, depth: int = 2) -> str:
        res = querier.get_neighbors(target_id=target, depth=depth)
        return res.to_markdown_summary()

    def handle_shortest_path(source: str, target: str) -> str:
        edges = querier.shortest_path(source_query=source, target_query=target)
        if not edges:
            return f"No path found between `{source}` and `{target}`."
        steps = [f"`{e.source}` --[{e.relation}]--> `{e.target}`" for e in edges]
        return "Shortest Path:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

    return {
        "graphify:query_graph": {
            "handler": handle_query_graph,
            "schema": {
                "type": "function",
                "function": {
                    "name": "graphify_query_graph",
                    "description": "Search the Graphify AST/knowledge graph for files, classes, functions, or docs matching a keyword.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Symbol, filename, or concept to search."},
                            "limit": {"type": "integer", "default": 15},
                        },
                        "required": ["query"],
                    },
                },
            },
        },
        "graphify:get_neighbors": {
            "handler": handle_get_neighbors,
            "schema": {
                "type": "function",
                "function": {
                    "name": "graphify_get_neighbors",
                    "description": "Explore the k-hop call/dependency neighborhood around a Graphify node.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "Node ID or symbol name."},
                            "depth": {"type": "integer", "default": 2},
                        },
                        "required": ["target"],
                    },
                },
            },
        },
        "graphify:shortest_path": {
            "handler": handle_shortest_path,
            "schema": {
                "type": "function",
                "function": {
                    "name": "graphify_shortest_path",
                    "description": "Find the shortest dependency or call path between two symbols/files in the Graphify graph.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "Starting node/symbol."},
                            "target": {"type": "string", "description": "Destination node/symbol."},
                        },
                        "required": ["source", "target"],
                    },
                },
            },
        },
    }
