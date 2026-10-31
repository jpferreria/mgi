from __future__ import annotations

from pathlib import Path

ROOT_CONTEXT_MD = """# Workflow Routing: Generic AI Agent Stack (ICM + Graphify + Mem0)

## Overview
A glass-box, four-stage autonomous agent pipeline built on the **Interpretable Context Methodology (ICM)**, **Graphify** structural knowledge graphs, and **Mem0** persistent memory.

## Stage Map (Execution Order)
1. **`01_discover/`** — Queries Graphify AST clusters and Mem0 history to map impacted symbols and constraints.
2. **`02_plan/`** — Synthesizes the discovery manifest into a concrete, step-by-step implementation blueprint.
3. **`03_execute/`** — Applies targeted code/artifact changes strictly scoped to the approved blueprint.
4. **`04_verify/`** — Evaluates deliverables against quality gates and consolidates long-term lessons into Mem0.

## Global Rules & Constraints
- **Unidirectional Flow**: Downstream stages read upstream `output/` artifacts; upstream stages never depend on downstream files.
- **Token Discipline**: Each stage operates within a focused 2,000–8,000 token window assembled by the 5-Layer Context Compiler.
"""

IDENTITY_MD = """# Layer 1: Agent Identity & Operating Persona

You are an **ICM Stage Compiler Agent** powered by **Graphify** (structural AST awareness) and **Mem0** (persistent episodic & semantic memory).

## Core Operating Principles
- **Prefer Structural Graph Queries over Blind File Dumps**: Always consult the Graphify subgraph in Layer 4 before reading raw files.
- **Anchor Decisions to Graph Nodes**: When recording findings or memories in Mem0, reference exact symbol/file IDs.
- **Strict Contract Compliance**: Only write to the files declared in `## 3. Outputs` of the active Stage Contract.
"""

CONSTRAINTS_MD = """# Global Workspace Constraints

- Maintain modular, well-typed code and preserve existing documentation integrity.
- Keep stage deliverables concise and structured so downstream stages stay within their token budgets.
"""

TASK_SPEC_MD = """# Task Specification

## Objective
Analyze the workspace architecture, design a modular enhancement, execute the specification, and verify all quality gates.
"""

STAGE_01_DISCOVER = """---
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
"""

STAGE_02_PLAN = """---
stage_id: "02_plan"
name: "Implementation Blueprint & Design"
max_context_tokens: 6000
hitl_checkpoint: false
mem0:
  recall_query: "design patterns, architectural decisions, interface contracts"
  recall_top_k: 5
  auto_extract_on_complete: true
graphify:
  auto_refresh: false
  seed_queries:
    - type: "community_summary"
tools:
  - "graphify:query_graph"
  - "graphify:shortest_path"
  - "mem0:search_memory"
  - "mem0:add_memory"
  - "fs:write_output"
---

# Stage Contract: 02_plan

## 1. Inputs (What to Read)
- Discovery impact analysis: `../01_discover/output/impact_analysis.md`
- Discovery manifest: `../01_discover/output/context_manifest.json`

## 2. Process (What to Do)
- Translate the discovery impact analysis into an ordered, verifiable implementation plan.
- Record any major architectural trade-offs into Mem0.

## 3. Outputs (What to Write)
- `output/implementation_blueprint.md`: Step-by-step execution specification and verification criteria.

## 4. Quality Gates & Checkpoints
- [ ] `output/implementation_blueprint.md` specifies exact target files and test cases.
"""

STAGE_03_EXECUTE = """---
stage_id: "03_execute"
name: "Scoped Execution & Synthesis"
max_context_tokens: 7000
hitl_checkpoint: false
mem0:
  recall_query: "coding standards, bug resolutions, implementation details"
  recall_top_k: 5
  auto_extract_on_complete: true
graphify:
  auto_refresh: false
  seed_queries:
    - type: "neighbors"
      target: "{{input.focal_symbol}}"
      depth: 1
tools:
  - "graphify:get_neighbors"
  - "mem0:search_memory"
  - "mem0:add_memory"
  - "fs:read_lines"
  - "fs:write_output"
---

# Stage Contract: 03_execute

## 1. Inputs (What to Read)
- Implementation blueprint: `../02_plan/output/implementation_blueprint.md`

## 2. Process (What to Do)
- Execute the changes and artifacts specified in `implementation_blueprint.md`.
- Log completed changes and touched Graphify nodes in the execution log.

## 3. Outputs (What to Write)
- `output/execution_log.md`: Summary of synthesized changes, modified symbols, and rationale.

## 4. Quality Gates & Checkpoints
- [ ] All steps in `implementation_blueprint.md` are accounted for in `output/execution_log.md`.
"""

STAGE_04_VERIFY = """---
stage_id: "04_verify"
name: "Quality Verification & Memory Consolidation"
max_context_tokens: 5000
hitl_checkpoint: false
mem0:
  recall_query: "verification checklists, regression risks, quality gates"
  recall_top_k: 5
  auto_extract_on_complete: true
graphify:
  auto_refresh: true
  seed_queries:
    - type: "community_summary"
tools:
  - "graphify:query_graph"
  - "mem0:search_memory"
  - "mem0:add_memory"
  - "fs:write_output"
---

# Stage Contract: 04_verify

## 1. Inputs (What to Read)
- Implementation blueprint: `../02_plan/output/implementation_blueprint.md`
- Execution log: `../03_execute/output/execution_log.md`

## 2. Process (What to Do)
- Refresh the Graphify structural graph and verify architectural integrity.
- Consolidate reusable lessons, resolved pitfalls, and updated symbol relationships into Mem0.

## 3. Outputs (What to Write)
- `output/verification_report.md`: Final sign-off report and consolidated memory digest.

## 4. Quality Gates & Checkpoints
- [ ] `output/verification_report.md` confirms all upstream quality gates passed.
"""


def scaffold_icm_workspace(target_dir: Path, overwrite: bool = False) -> list[Path]:
    """
    Scaffolds a complete 5-Layer ICM workspace directory structure (`CONTEXT.md`, `_config/`,
    `_input/`, and `01_discover` through `04_verify`) at `target_dir`.
    """
    root = target_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)

    files_to_write: dict[Path, str] = {
        root / "CONTEXT.md": ROOT_CONTEXT_MD,
        root / "_config" / "IDENTITY.md": IDENTITY_MD,
        root / "_config" / "CONSTRAINTS.md": CONSTRAINTS_MD,
        root / "_input" / "task_spec.md": TASK_SPEC_MD,
        root / "01_discover" / "CONTEXT.md": STAGE_01_DISCOVER,
        root / "02_plan" / "CONTEXT.md": STAGE_02_PLAN,
        root / "03_execute" / "CONTEXT.md": STAGE_03_EXECUTE,
        root / "04_verify" / "CONTEXT.md": STAGE_04_VERIFY,
    }

    written: list[Path] = []
    for path, content in files_to_write.items():
        if path.exists() and not overwrite:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        written.append(path)

    for stage_name in ("01_discover", "02_plan", "03_execute", "04_verify"):
        (root / stage_name / "output").mkdir(parents=True, exist_ok=True)

    return written
