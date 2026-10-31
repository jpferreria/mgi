---
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
