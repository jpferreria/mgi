# Graphify Architectural Knowledge Report

- **Total Nodes**: 149
- **Total Edges**: 1093
- **Detected Communities (Subsystems)**: 9

## Communities / Functional Clusters
- **Community `0` (`01_discover`)**: 3 nodes
- **Community `1` (`02_plan`)**: 2 nodes
- **Community `2` (`03_execute`)**: 2 nodes
- **Community `3` (`04_verify`)**: 1 nodes
- **Community `4` (`root`)**: 3 nodes
- **Community `5` (`_config`)**: 2 nodes
- **Community `6` (`_input`)**: 1 nodes
- **Community `7` (`src`)**: 128 nodes
- **Community `8` (`tests`)**: 7 nodes

## High-Centrality Nodes (Architectural Hubs)
- `src/mem_graph_icm/graph/querier.py::GraphifyQuerier.load` (method, degree=43, community=7)
- `src/mem_graph_icm/icm/compiler.py::ICMContextCompiler.compile_stage_context` (method, degree=40, community=7)
- `src/mem_graph_icm/icm/compiler.py::ICMContextCompiler._build_layer4_reference` (method, degree=29, community=7)
- `src/mem_graph_icm/icm/parser.py::ICMParser.parse_stage` (method, degree=27, community=7)
- `src/mem_graph_icm/cli.py::cmd_compile` (function, degree=26, community=7)
- `src/mem_graph_icm/graph/indexer.py::GraphifyIndexer._build_fallback_graph` (method, degree=26, community=7)
- `src/mem_graph_icm/memory/manager.py::Mem0LocalManager._search_local_store` (method, degree=24, community=7)
- `src/mem_graph_icm/agent/loop.py::StageAgentLoop.execute` (method, degree=23, community=7)
- `src/mem_graph_icm/cli.py` (file, degree=23, community=7)
- `src/mem_graph_icm/cli.py::cmd_run` (function, degree=22, community=7)
