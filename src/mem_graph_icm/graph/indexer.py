from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from mem_graph_icm.config import MGIConfig


class GraphifyIndexer:
    """
    Wraps the `graphify` (`graphifyy`) CLI/library to index a codebase or workspace into
    `graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md`.

    Includes a deterministic built-in AST + Markdown graph builder fallback so the stack works
    seamlessly even in offline or minimal environments where the `graphify` CLI binary has not
    yet been initialized.
    """

    def __init__(self, config: MGIConfig) -> None:
        self.config = config
        self.workspace_root = config.workspace_root

    def build_or_refresh(self, target_dir: Path | None = None, force_native_cli: bool = False) -> Path:
        """
        Run `graphify` on `target_dir` (defaults to `workspace_root`).
        Returns the path to the generated `graph.json`.
        """
        target = (target_dir or self.workspace_root).resolve()
        out_dir = (self.workspace_root / self.config.graphify.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        graphify_bin = shutil.which("graphify")
        if graphify_bin:
            try:
                proc = subprocess.run(
                    [graphify_bin, str(target)],
                    cwd=str(self.workspace_root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                graph_path = self.config.graphify.graph_json_path(self.workspace_root)
                if proc.returncode == 0 and graph_path.exists():
                    return graph_path
            except Exception:
                if force_native_cli:
                    raise

        if force_native_cli:
            raise RuntimeError("`graphify` CLI binary not found or failed to generate graph.json")

        # Deterministic local AST + Markdown fallback builder (compatible with Graphify JSON schema)
        return self._build_fallback_graph(target, out_dir)

    def _build_fallback_graph(self, target: Path, out_dir: Path) -> Path:
        nodes: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        node_ids: set[str] = set()

        ignore_dirs = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            ".mgi_storage",
            "graphify-out",
            ".pytest_cache",
        }

        def add_node(
            node_id: str,
            label: str,
            node_type: str,
            file_path: str,
            community: int,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            if node_id not in node_ids:
                node_ids.add(node_id)
                nodes.append(
                    {
                        "id": node_id,
                        "label": label,
                        "type": node_type,
                        "file": file_path,
                        "community": community,
                        "metadata": metadata or {},
                    }
                )

        def add_edge(source: str, target_id: str, relation: str) -> None:
            links.append({"source": source, "target": target_id, "relation": relation})

        # Assign Leiden-like community IDs grouped by top-level module/folder
        community_map: dict[str, int] = {}

        def get_community(rel_path: Path) -> int:
            top = rel_path.parts[0] if len(rel_path.parts) > 1 else "root"
            if top not in community_map:
                community_map[top] = len(community_map)
            return community_map[top]

        for path in sorted(target.rglob("*")):
            if any(part in ignore_dirs for part in path.parts):
                continue
            if not path.is_file():
                continue

            rel_path = path.relative_to(target)
            rel_str = rel_path.as_posix()
            comm = get_community(rel_path)

            if path.suffix == ".py":
                add_node(rel_str, path.name, "file", rel_str, comm)
                self._parse_python_ast(path, rel_str, comm, add_node, add_edge)
            elif path.suffix in {".md", ".toml", ".yaml", ".yml", ".json"}:
                add_node(rel_str, path.name, "document", rel_str, comm)
                if path.suffix == ".md":
                    self._parse_markdown_links(path, rel_str, comm, add_node, add_edge)

        # Compute degree centrality to identify architectural "god nodes"
        degrees: dict[str, int] = defaultdict(int)
        for edge in links:
            degrees[edge["source"]] += 1
            degrees[edge["target"]] += 1

        for node in nodes:
            node["degree"] = degrees.get(node["id"], 0)

        graph_payload = {
            "directed": True,
            "multigraph": False,
            "graph": {
                "generator": "mem-graph-icm/graphify-compatible",
                "workspace": str(target),
                "communities": {v: k for k, v in community_map.items()},
            },
            "nodes": nodes,
            "links": links,
        }

        graph_json_path = out_dir / self.config.graphify.graph_json_name
        graph_json_path.write_text(json.dumps(graph_payload, indent=2), encoding="utf-8")

        report_md_path = out_dir / self.config.graphify.report_md_name
        report_md_path.write_text(
            self._generate_graph_report(nodes, links, community_map),
            encoding="utf-8",
        )
        return graph_json_path

    def _parse_python_ast(
        self,
        file_path: Path,
        rel_str: str,
        community: int,
        add_node: Any,
        add_edge: Any,
    ) -> None:
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel_str)
        except Exception:
            return

        for item in tree.body:
            if isinstance(item, ast.ClassDef):
                cls_id = f"{rel_str}::{item.name}"
                doc = ast.get_docstring(item) or ""
                add_node(
                    cls_id,
                    item.name,
                    "class",
                    rel_str,
                    community,
                    {"lineno": item.lineno, "doc": doc[:200]},
                )
                add_edge(rel_str, cls_id, "defines_class")
                for sub in item.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_id = f"{cls_id}.{sub.name}"
                        add_node(
                            m_id,
                            f"{item.name}.{sub.name}",
                            "method",
                            rel_str,
                            community,
                            {"lineno": sub.lineno},
                        )
                        add_edge(cls_id, m_id, "defines_method")
                        self._extract_calls(sub, m_id, add_edge)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_id = f"{rel_str}::{item.name}"
                doc = ast.get_docstring(item) or ""
                add_node(
                    fn_id,
                    item.name,
                    "function",
                    rel_str,
                    community,
                    {"lineno": item.lineno, "doc": doc[:200]},
                )
                add_edge(rel_str, fn_id, "defines_function")
                self._extract_calls(item, fn_id, add_edge)
            elif isinstance(item, ast.Import):
                for alias in item.names:
                    add_edge(rel_str, alias.name, "imports")
            elif isinstance(item, ast.ImportFrom) and item.module:
                add_edge(rel_str, item.module, "imports_from")

    def _extract_calls(self, fn_node: ast.AST, caller_id: str, add_edge: Any) -> None:
        for child in ast.walk(fn_node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    add_edge(caller_id, child.func.id, "calls")
                elif isinstance(child.func, ast.Attribute):
                    add_edge(caller_id, child.func.attr, "calls_attr")

    def _parse_markdown_links(
        self,
        file_path: Path,
        rel_str: str,
        community: int,
        add_node: Any,
        add_edge: Any,
    ) -> None:
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            return
        # Extract headings and file references
        for match in re.finditer(r"`([a-zA-Z0-9_./-]+\.(?:py|md|json|yaml))`", text):
            ref = match.group(1)
            add_edge(rel_str, ref, "references_path")

    def _generate_graph_report(
        self,
        nodes: list[dict[str, Any]],
        links: list[dict[str, Any]],
        community_map: dict[str, int],
    ) -> str:
        top_nodes = sorted(nodes, key=lambda n: n.get("degree", 0), reverse=True)[:10]
        lines = [
            "# Graphify Architectural Knowledge Report",
            "",
            f"- **Total Nodes**: {len(nodes)}",
            f"- **Total Edges**: {len(links)}",
            f"- **Detected Communities (Subsystems)**: {len(community_map)}",
            "",
            "## Communities / Functional Clusters",
        ]
        for name, cid in community_map.items():
            count = sum(1 for n in nodes if n.get("community") == cid)
            lines.append(f"- **Community `{cid}` (`{name}`)**: {count} nodes")

        lines.extend(["", "## High-Centrality Nodes (Architectural Hubs)"])
        for n in top_nodes:
            lines.append(
                f"- `{n['id']}` ({n['type']}, degree={n.get('degree', 0)}, community={n.get('community')})"
            )

        return "\n".join(lines) + "\n"
