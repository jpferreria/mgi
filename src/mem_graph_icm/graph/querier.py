from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mem_graph_icm.config import MGIConfig


class GraphNode(BaseModel):
    id: str
    label: str = ""
    type: str = "unknown"
    file: str = ""
    community: int | None = None
    degree: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str = "related_to"


class SubgraphResult(BaseModel):
    focal_query: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def to_markdown_summary(self, max_nodes: int = 25) -> str:
        if not self.nodes:
            return f"*No Graphify nodes matched query `{self.focal_query}`.*"

        lines = [
            f"### Graphify Subgraph (`{self.focal_query}`)",
            f"Nodes ({ min(len(self.nodes), max_nodes) }/{len(self.nodes)}):",
        ]
        for node in self.nodes[:max_nodes]:
            loc = f" in `{node.file}`" if node.file and node.file != node.id else ""
            comm = f" [cluster={node.community}]" if node.community is not None else ""
            lines.append(f"- `{node.id}` ({node.type}){loc}{comm}")

        if self.edges:
            lines.append("\nKey Relationships:")
            for edge in self.edges[: max_nodes * 2]:
                lines.append(f"- `{edge.source}` --[{edge.relation}]--> `{edge.target}`")

        return "\n".join(lines)


class GraphifyQuerier:
    """
    Loads `graphify-out/graph.json` and exposes low-token graph traversals:
    - Keyword / symbol node search (`query_graph`)
    - K-hop BFS neighborhood expansion (`get_neighbors`)
    - Shortest dependency/call path (`shortest_path`)
    - Leiden community / cluster overview (`community_summary`)
    """

    def __init__(self, config: MGIConfig) -> None:
        self.config = config
        self._nodes_by_id: dict[str, GraphNode] = {}
        self._adj: dict[str, list[GraphEdge]] = {}
        self._rev_adj: dict[str, list[GraphEdge]] = {}
        self._communities: dict[int, str] = {}
        self._loaded = False

    def load(self, graph_path: Path | None = None) -> bool:
        path = graph_path or self.config.graphify.graph_json_path(self.config.workspace_root)
        if not path.exists():
            self._loaded = False
            return False

        raw = json.loads(path.read_text(encoding="utf-8"))
        self._nodes_by_id.clear()
        self._adj.clear()
        self._rev_adj.clear()

        graph_meta = raw.get("graph", {})
        raw_comms = graph_meta.get("communities", {})
        self._communities = {int(k): str(v) for k, v in raw_comms.items() if str(k).isdigit()}

        for item in raw.get("nodes", []):
            node_id = str(item.get("id", ""))
            if not node_id:
                continue
            node = GraphNode(
                id=node_id,
                label=str(item.get("label", node_id)),
                type=str(item.get("type", "node")),
                file=str(item.get("file", "")),
                community=item.get("community"),
                degree=int(item.get("degree", 0)),
                metadata=item.get("metadata", {}) or {},
            )
            self._nodes_by_id[node_id] = node

        edge_list = raw.get("links") or raw.get("edges") or []
        for item in edge_list:
            src = str(item.get("source", ""))
            dst = str(item.get("target", ""))
            rel = str(item.get("relation") or item.get("label") or "links_to")
            if not src or not dst:
                continue
            edge = GraphEdge(source=src, target=dst, relation=rel)
            self._adj.setdefault(src, []).append(edge)
            self._rev_adj.setdefault(dst, []).append(edge)

        self._loaded = True
        return True

    def ensure_loaded(self) -> bool:
        if not self._loaded:
            return self.load()
        return True

    def query_graph(self, query: str, limit: int = 15) -> SubgraphResult:
        """Search nodes by substring match on ID, label, type, or file path."""
        if not self.ensure_loaded():
            return SubgraphResult(focal_query=query)

        q_lower = query.lower().strip()
        matched: list[GraphNode] = []
        for node in self._nodes_by_id.values():
            if (
                q_lower in node.id.lower()
                or q_lower in node.label.lower()
                or q_lower in node.file.lower()
                or q_lower == node.type.lower()
            ):
                matched.append(node)

        matched.sort(key=lambda n: n.degree, reverse=True)
        selected = matched[:limit]
        selected_ids = {n.id for n in selected}

        edges: list[GraphEdge] = []
        for nid in selected_ids:
            for e in self._adj.get(nid, []):
                if e.target in selected_ids or len(edges) < limit * 2:
                    edges.append(e)

        return SubgraphResult(focal_query=query, nodes=selected, edges=edges)

    def get_neighbors(self, target_id: str, depth: int = 2, max_nodes: int = 30) -> SubgraphResult:
        """Run bidirectional BFS up to `depth` hops around `target_id` (or closest matching node)."""
        if not self.ensure_loaded():
            return SubgraphResult(focal_query=target_id)

        start_id = self._resolve_node_id(target_id)
        if not start_id:
            return SubgraphResult(focal_query=target_id)

        visited_nodes: dict[str, GraphNode] = {}
        collected_edges: list[GraphEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()

        queue: deque[tuple[str, int]] = deque([(start_id, 0)])
        visited_distances: dict[str, int] = {start_id: 0}

        while queue and len(visited_nodes) < max_nodes:
            curr_id, dist = queue.popleft()
            if curr_id in self._nodes_by_id:
                visited_nodes[curr_id] = self._nodes_by_id[curr_id]
            else:
                visited_nodes[curr_id] = GraphNode(id=curr_id, label=curr_id, type="external_symbol")

            if dist >= depth:
                continue

            neighbors = self._adj.get(curr_id, []) + self._rev_adj.get(curr_id, [])
            for edge in neighbors:
                edge_key = (edge.source, edge.target, edge.relation)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    collected_edges.append(edge)

                other = edge.target if edge.source == curr_id else edge.source
                if other not in visited_distances and len(visited_nodes) < max_nodes:
                    visited_distances[other] = dist + 1
                    queue.append((other, dist + 1))

        return SubgraphResult(
            focal_query=f"neighbors({start_id}, depth={depth})",
            nodes=list(visited_nodes.values()),
            edges=collected_edges,
        )

    def shortest_path(self, source_query: str, target_query: str) -> list[GraphEdge]:
        """Find the shortest undirected dependency/call path between two symbols/files."""
        if not self.ensure_loaded():
            return []

        src_id = self._resolve_node_id(source_query)
        dst_id = self._resolve_node_id(target_query)
        if not src_id or not dst_id or src_id == dst_id:
            return []

        queue: deque[str] = deque([src_id])
        parent_edge: dict[str, tuple[str, GraphEdge]] = {}
        visited: set[str] = {src_id}

        while queue:
            curr = queue.popleft()
            if curr == dst_id:
                path: list[GraphEdge] = []
                step = dst_id
                while step != src_id:
                    prev, edge = parent_edge[step]
                    path.append(edge)
                    step = prev
                path.reverse()
                return path

            for edge in self._adj.get(curr, []) + self._rev_adj.get(curr, []):
                nxt = edge.target if edge.source == curr else edge.source
                if nxt not in visited:
                    visited.add(nxt)
                    parent_edge[nxt] = (curr, edge)
                    queue.append(nxt)

        return []

    def community_summary(self) -> str:
        """Return a concise overview of Leiden clusters and high-centrality hubs."""
        report_path = self.config.graphify.report_md_path(self.config.workspace_root)
        if report_path.exists():
            return report_path.read_text(encoding="utf-8").strip()

        if not self.ensure_loaded():
            return "*Graphify index not yet built. Run `mgi index` first.*"

        top = sorted(self._nodes_by_id.values(), key=lambda n: n.degree, reverse=True)[:10]
        lines = [
            f"Graphify Summary ({len(self._nodes_by_id)} nodes):",
            *(f"- `{n.id}` ({n.type}, degree={n.degree})" for n in top),
        ]
        return "\n".join(lines)

    def _resolve_node_id(self, query: str) -> str | None:
        if query in self._nodes_by_id:
            return query
        q_lower = query.lower().strip()
        for nid, node in self._nodes_by_id.items():
            if nid.lower() == q_lower or node.label.lower() == q_lower:
                return nid
        for nid, node in self._nodes_by_id.items():
            if q_lower in nid.lower() or q_lower in node.label.lower():
                return nid
        return None
