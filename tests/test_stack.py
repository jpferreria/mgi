from __future__ import annotations

from pathlib import Path

from mem_graph_icm.config import get_config
from mem_graph_icm.graph.indexer import GraphifyIndexer
from mem_graph_icm.graph.querier import GraphifyQuerier
from mem_graph_icm.icm.compiler import ICMContextCompiler
from mem_graph_icm.icm.parser import ICMParser
from mem_graph_icm.icm.runner import ICMPipelineRunner
from mem_graph_icm.memory.lifecycle import StageMemoryLifecycle
from mem_graph_icm.memory.manager import Mem0LocalManager
from mem_graph_icm.templates import scaffold_icm_workspace


def _create_sample_codebase(root: Path) -> None:
    src_dir = root / "app"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "auth.py").write_text(
        '''"""Authentication service module."""

class TokenValidator:
    def verify_jwt(self, token: str) -> bool:
        return len(token) > 10

class AuthService:
    def __init__(self) -> None:
        self.validator = TokenValidator()

    def authenticate_user(self, username: str, token: str) -> bool:
        return self.validator.verify_jwt(token)
''',
        encoding="utf-8",
    )


def test_scaffold_and_parse_icm_workspace(tmp_path: Path) -> None:
    written = scaffold_icm_workspace(tmp_path)
    assert len(written) == 8

    ws = ICMParser.parse_workspace(tmp_path)
    assert len(ws.stage_dirs) == 4
    assert [d.name for d in ws.stage_dirs] == [
        "01_discover",
        "02_plan",
        "03_execute",
        "04_verify",
    ]

    s1 = ICMParser.parse_stage(tmp_path / "01_discover")
    assert s1.stage_id == "01_discover"
    assert s1.max_context_tokens == 6000
    assert "output/impact_analysis.md" in s1.expected_output_paths
    assert "output/context_manifest.json" in s1.expected_output_paths
    assert s1.line_count <= 80


def test_graphify_indexer_and_querier(tmp_path: Path) -> None:
    _create_sample_codebase(tmp_path)
    scaffold_icm_workspace(tmp_path)

    cfg = get_config(tmp_path)
    indexer = GraphifyIndexer(cfg)
    graph_path = indexer.build_or_refresh()
    assert graph_path.exists()

    querier = GraphifyQuerier(cfg)
    assert querier.load(graph_path) is True

    # Search for AuthService
    res = querier.query_graph("AuthService")
    assert any("AuthService" in n.id for n in res.nodes)

    # Check 2-hop neighborhood around AuthService.authenticate_user
    neigh = querier.get_neighbors("authenticate_user", depth=2)
    node_ids = {n.id for n in neigh.nodes}
    assert any("authenticate_user" in nid for nid in node_ids)
    assert any("verify_jwt" in nid for nid in node_ids)

    # Shortest path between file and method
    path_edges = querier.shortest_path("app/auth.py", "authenticate_user")
    assert len(path_edges) >= 1


def test_mem0_local_manager_with_graph_anchors(tmp_path: Path) -> None:
    cfg = get_config(tmp_path)
    mgr = Mem0LocalManager(cfg, force_fallback=True)

    rec1 = mgr.add_memory(
        "AuthService requires strict JWT expiration validation in TokenValidator.",
        stage_id="01_discover",
        graph_nodes=["app/auth.py::AuthService", "app/auth.py::TokenValidator"],
        scope="project",
    )
    assert rec1.id

    mgr.add_memory(
        "Unrelated database connection pooling note.",
        stage_id="01_discover",
        graph_nodes=["app/db.py::Pool"],
        scope="project",
    )

    # Search with overlapping Graphify node anchor should rank rec1 first
    results = mgr.search_memories(
        query="validation rules",
        graph_nodes=["app/auth.py::AuthService"],
        top_k=2,
    )
    assert len(results) >= 1
    assert "AuthService" in results[0].memory


def test_five_layer_context_compiler_token_budget(tmp_path: Path) -> None:
    _create_sample_codebase(tmp_path)
    scaffold_icm_workspace(tmp_path)

    cfg = get_config(tmp_path)
    GraphifyIndexer(cfg).build_or_refresh()
    querier = GraphifyQuerier(cfg)
    querier.load()

    mem_mgr = Mem0LocalManager(cfg, force_fallback=True)
    mem_mgr.add_memory(
        "Always prefer hexagonal adapters around AuthService.",
        scope="global",
        graph_nodes=["app/auth.py::AuthService"],
    )

    compiler = ICMContextCompiler(cfg, querier, StageMemoryLifecycle(mem_mgr))
    ws = ICMParser.parse_workspace(tmp_path)
    stage = ICMParser.parse_stage(tmp_path / "01_discover")

    # Force a tight token budget (e.g., 450 tokens) to verify automatic pruning
    stage.max_context_tokens = 450
    compiled = compiler.compile_stage_context(
        workspace=ws,
        stage=stage,
        template_vars={"focal_symbol": "AuthService"},
    )
    assert compiled.estimated_tokens <= 450
    assert len(compiled.pruned_layers) >= 1
    assert "ICM LAYER 1" in compiled.render_system_prompt()
    assert "ICM LAYER 4" in compiled.render_user_prompt()


def test_end_to_end_icm_pipeline_execution(tmp_path: Path) -> None:
    _create_sample_codebase(tmp_path)
    scaffold_icm_workspace(tmp_path)

    cfg = get_config(tmp_path)
    runner = ICMPipelineRunner(cfg, force_local_memory_fallback=True)

    results = runner.run_pipeline(
        template_vars={"focal_symbol": "AuthService"},
        dry_run=True,
    )
    assert len(results) == 4
    assert [r.status for r in results] == [
        "completed",
        "completed",
        "completed",
        "completed",
    ]

    # Verify all stage deliverables exist on disk
    assert (tmp_path / "01_discover" / "output" / "impact_analysis.md").exists()
    assert (tmp_path / "01_discover" / "output" / "context_manifest.json").exists()
    assert (tmp_path / "02_plan" / "output" / "implementation_blueprint.md").exists()
    assert (tmp_path / "03_execute" / "output" / "execution_log.md").exists()
    assert (tmp_path / "04_verify" / "output" / "verification_report.md").exists()

    # Verify memories were consolidated into Mem0 across stages
    all_memories = runner.mem_manager.get_all_memories()
    assert len(all_memories) >= 4
