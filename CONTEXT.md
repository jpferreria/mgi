# Workflow Routing: Generic AI Agent Stack (ICM + Graphify + Mem0)

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
