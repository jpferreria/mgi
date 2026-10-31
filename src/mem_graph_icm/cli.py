from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mem_graph_icm.config import get_config
from mem_graph_icm.graph.indexer import GraphifyIndexer
from mem_graph_icm.graph.querier import GraphifyQuerier
from mem_graph_icm.icm.compiler import ICMContextCompiler
from mem_graph_icm.icm.parser import ICMParser
from mem_graph_icm.icm.runner import ICMPipelineRunner
from mem_graph_icm.memory.lifecycle import StageMemoryLifecycle
from mem_graph_icm.memory.manager import Mem0LocalManager
from mem_graph_icm.templates import scaffold_icm_workspace

app = typer.Typer(
    name="mgi",
    help="mem-graph-icm (`mgi`): Generic AI Agent Stack combining ICM, Graphify, and Mem0.",
    add_completion=False,
)
console = Console()


@app.command("init")
def cmd_init(
    workspace: Path = typer.Argument(Path("."), help="Target directory for the ICM workspace."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing CONTEXT.md files."),
    index_now: bool = typer.Option(True, "--index/--no-index", help="Build initial Graphify graph."),
) -> None:
    """Scaffold a 5-Layer Interpretable Context Methodology (ICM) workspace and initialize Graphify."""
    root = workspace.resolve()
    written = scaffold_icm_workspace(root, overwrite=overwrite)
    console.print(
        Panel(
            f"Initialized ICM workspace at [bold cyan]{root}[/bold cyan]\n"
            f"Created/Updated [bold]{len(written)}[/bold] contract & configuration files.",
            title="mgi init",
            border_style="green",
        )
    )
    if index_now:
        cfg = get_config(root)
        graph_path = GraphifyIndexer(cfg).build_or_refresh()
        console.print(f"[green]✓[/green] Built Graphify knowledge graph at [bold]{graph_path}[/bold]")


@app.command("index")
def cmd_index(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
) -> None:
    """Index the codebase and ICM markdown contracts into `graphify-out/graph.json`."""
    cfg = get_config(workspace)
    indexer = GraphifyIndexer(cfg)
    graph_path = indexer.build_or_refresh()
    querier = GraphifyQuerier(cfg)
    querier.load(graph_path)
    console.print(
        Panel(
            querier.community_summary(),
            title=f"Graphify Index Built ({graph_path.name})",
            border_style="cyan",
        )
    )


@app.command("compile")
def cmd_compile(
    stage_id: str = typer.Argument(..., help="Stage folder name (e.g. `01_discover`)."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
    focal_symbol: str = typer.Option("", "--symbol", "-s", help="Focal Graphify symbol/file."),
) -> None:
    """Compile and inspect the 5-Layer ICM context window for a single stage."""
    cfg = get_config(workspace)
    ws_contract = ICMParser.parse_workspace(cfg.workspace_root)
    stage_contract = ICMParser.parse_stage(cfg.workspace_root / stage_id)

    querier = GraphifyQuerier(cfg)
    querier.ensure_loaded()
    mem_mgr = Mem0LocalManager(cfg)
    compiler = ICMContextCompiler(cfg, querier, StageMemoryLifecycle(mem_mgr))

    compiled = compiler.compile_stage_context(
        workspace=ws_contract,
        stage=stage_contract,
        template_vars={"focal_symbol": focal_symbol} if focal_symbol else {},
    )

    console.print(
        Panel(
            f"[bold]Stage[/bold]: {compiled.stage_id}\n"
            f"[bold]Token Budget[/bold]: {compiled.estimated_tokens} / {compiled.max_tokens} tokens\n"
            f"[bold]Pruned Layers[/bold]: {', '.join(compiled.pruned_layers) or 'None'}\n"
            f"[bold]Active Graphify Nodes[/bold]: {len(compiled.active_graph_nodes)}\n"
            f"[bold]Recalled Mem0 Facts[/bold]: {len(compiled.recalled_memory_ids)}",
            title="ICM 5-Layer Context Compilation",
            border_style="magenta",
        )
    )
    console.print("\n[bold underline]System Prompt (Layers 1–3):[/bold underline]")
    console.print(compiled.render_system_prompt())
    console.print("\n[bold underline]User Prompt (Layers 4–5):[/bold underline]")
    console.print(compiled.render_user_prompt())


@app.command("run")
def cmd_run(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
    stage: Optional[str] = typer.Option(None, "--stage", help="Run only a specific stage folder."),
    focal_symbol: str = typer.Option("", "--symbol", "-s", help="Focal Graphify symbol/file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Deterministic synthesis without LLM calls."),
    auto_approve: bool = typer.Option(False, "--yes", "-y", help="Auto-approve HITL checkpoints."),
) -> None:
    """Execute the sequential ICM pipeline (`01_discover` -> `04_verify`) with Graphify and Mem0."""
    cfg = get_config(workspace)
    runner = ICMPipelineRunner(cfg)
    results = runner.run_pipeline(
        target_stage=stage,
        template_vars={"focal_symbol": focal_symbol} if focal_symbol else {},
        auto_approve_hitl=auto_approve,
        dry_run=dry_run,
    )

    table = Table(title="ICM Pipeline Execution Summary")
    table.add_column("Stage", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Tokens (Est/Max)", justify="right")
    table.add_column("Outputs Created", justify="right")
    table.add_column("Mem0 Facts Stored", justify="right")

    for r in results:
        status_color = "green" if r.status == "completed" else ("yellow" if r.status == "paused_hitl" else "red")
        table.add_row(
            r.stage_id,
            f"[{status_color}]{r.status}[/{status_color}]",
            f"{r.compiled_context.estimated_tokens}/{r.compiled_context.max_tokens}",
            str(len(r.validation.created_outputs)),
            str(r.stored_memories_count),
        )

    console.print(table)


@app.command("memory")
def cmd_memory(
    action: str = typer.Argument("list", help="Action: `list`, `search`, or `add`."),
    query_or_text: str = typer.Argument("", help="Search query or memory text to add."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
    stage_id: str = typer.Option("global", "--stage", help="Stage tag for new memory."),
) -> None:
    """Inspect, search, or add persistent memories in the local Mem0 store."""
    cfg = get_config(workspace)
    mgr = Mem0LocalManager(cfg)

    if action == "add":
        if not query_or_text:
            raise typer.BadParameter("Provide text to store when using `mgi memory add`.")
        rec = mgr.add_memory(query_or_text, stage_id=stage_id)
        console.print(f"[green]✓[/green] Stored memory [bold]{rec.id}[/bold]: {rec.memory}")
    elif action == "search":
        recs = mgr.search_memories(query_or_text or "*", top_k=10)
        console.print(json.dumps([r.model_dump() for r in recs], indent=2))
    else:
        recs = mgr.get_all_memories()
        console.print(json.dumps([r.model_dump() for r in recs], indent=2))


@app.command("mcp")
def cmd_mcp(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
) -> None:
    """Launch the unified `mem-graph-icm` Model Context Protocol (MCP) server over stdio."""
    from mem_graph_icm.agent.mcp_server import create_mcp_server

    server = create_mcp_server(workspace)
    if hasattr(server, "run"):
        server.run()
    else:
        console.print(
            "[yellow]FastMCP (`mcp` package) not installed in current environment; "
            "use `MGIMCPToolset` directly in Python or install `mcp>=1.0.0`.[/yellow]"
        )


if __name__ == "__main__":
    app()
