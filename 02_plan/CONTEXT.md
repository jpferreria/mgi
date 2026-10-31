---
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
