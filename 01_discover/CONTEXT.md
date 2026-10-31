---
stage_id: "01_discover"
name: "Architecture & Context Discovery"
max_context_tokens: 6000
hitl_checkpoint: false
mem0:
  recall_query: "architectural constraints, module bottlenecks, prior discovery findings"
  recall_top_k: 5
  auto_extract_on_complete: true
graphify:
  auto_refresh: false
  seed_queries:
    - type: "community_summary"
    - type: "neighbors"
      target: "{{input.focal_symbol}}"
      depth: 2
tools:
  - "graphify:query_graph"
  - "graphify:get_neighbors"
  - "graphify:shortest_path"
  - "mem0:search_memory"
  - "fs:read_lines"
  - "fs:write_output"
---

# Stage Contract: 01_discover

## 1. Inputs (What to Read)
- Task specification: `_input/task_spec.md`
- Graphify overview: `graphify-out/GRAPH_REPORT.md`

## 2. Process (What to Do)
- Inspect the Graphify community summary and k-hop neighborhood around the focal symbols.
- Cross-reference structural dependencies with recalled Mem0 memories.
- Identify the minimal set of files, classes, and functions impacted by the task.

## 3. Outputs (What to Write)
- `output/impact_analysis.md`: Breakdown of affected Graphify nodes, call paths, and risks.
- `output/context_manifest.json`: Structured list of focal nodes and files for `02_plan`.

## 4. Quality Gates & Checkpoints
- [ ] `output/impact_analysis.md` clearly lists target Graphify node IDs.
- [ ] `output/context_manifest.json` is valid JSON.
