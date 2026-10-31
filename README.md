# `mem-graph-icm` (`mgi`)

A local-first Python AI Agent SDK & CLI harness that unifies three complementary context-engineering pillars:

1. **ICM (*Interpretable Context Methodology*, arXiv:2603.16021)**: Replaces opaque multi-agent state graphs with a transparent, 5-Layer filesystem hierarchy (`CONTEXT.md`, `_config/`, and numbered stage directories `01_discover` $\rightarrow$ `04_verify`) enforcing strict $2\text{k}\text{–}8\text{k}$ token budgets per stage.
2. **Graphify (`graphifyy`)**: Deterministic Tree-sitter AST and document graph indexing with community clustering. Eliminates blind file dumps by providing targeted subgraph queries (`query_graph`, `get_neighbors`, `shortest_path`).
3. **Mem0 (`mem0ai`)**: Persistent episodic and semantic memory backed by zero-Docker local storage (embedded on-disk Qdrant + SQLite + local JSON fallback), with memories anchored directly to **Graphify node IDs** and **ICM stages**.

---

## Quick Start

### 1. Install
```bash
pip install -e ".[dev]"
```

### 2. Initialize a 5-Layer ICM Workspace & Build the Graphify Index
```bash
mgi init .
```
This scaffolds:
- `CONTEXT.md` (Layer 2 Root Routing Map)
- `_config/IDENTITY.md` & `_config/CONSTRAINTS.md` (Layer 1 Identity)
- `01_discover/CONTEXT.md`, `02_plan/CONTEXT.md`, `03_execute/CONTEXT.md`, `04_verify/CONTEXT.md` (Layer 3 Stage Contracts)
- `graphify-out/graph.json` & `graphify-out/GRAPH_REPORT.md` (Layer 4 Structural Reference)

### 3. Compile & Inspect a Stage's 5-Layer Prompt Window
```bash
mgi compile 01_discover --symbol ICMContextCompiler
```

### 4. Execute the End-to-End Pipeline
```bash
# Run with local Ollama / LiteLLM (or add --dry-run for deterministic offline verification)
mgi run --symbol ICMContextCompiler
```

### 5. Search or Add Graph-Anchored Persistent Memories (Mem0)
```bash
mgi memory add "Always cap Layer 4 Graphify subgraphs at 45% of remaining token budget" --stage 02_plan
mgi memory search "token budget"
```

### 6. Expose as an MCP Server for Coding Agents
```bash
mgi mcp
```
