---
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
