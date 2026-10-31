from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    """Configuration for LLM inference (defaults to local Ollama via LiteLLM)."""

    provider: Literal["ollama", "openai", "anthropic", "gemini", "litellm"] = Field(
        default_factory=lambda: os.environ.get("MGI_LLM_PROVIDER", "ollama")  # type: ignore[return-value]
    )
    model: str = Field(
        default_factory=lambda: os.environ.get("MGI_LLM_MODEL", "qwen2.5-coder:7b")
    )
    base_url: str | None = Field(
        default_factory=lambda: os.environ.get("MGI_LLM_BASE_URL", "http://localhost:11434")
    )
    temperature: float = 0.1
    max_tokens: int = 4096


class EmbedderConfig(BaseModel):
    """Configuration for local embeddings used by Mem0."""

    provider: Literal["ollama", "openai", "huggingface"] = Field(
        default_factory=lambda: os.environ.get("MGI_EMBED_PROVIDER", "ollama")  # type: ignore[return-value]
    )
    model: str = Field(
        default_factory=lambda: os.environ.get("MGI_EMBED_MODEL", "nomic-embed-text")
    )
    base_url: str | None = Field(
        default_factory=lambda: os.environ.get("MGI_EMBED_BASE_URL", "http://localhost:11434")
    )
    dims: int = 768


class Mem0StorageConfig(BaseModel):
    """Zero-Docker local-first configuration for Mem0 (Embedded Qdrant + SQLite)."""

    enabled: bool = True
    vector_provider: str = "qdrant"
    qdrant_path: Path = Field(default=Path(".mgi_storage/qdrant"))
    history_db_path: Path = Field(default=Path(".mgi_storage/mem0_history.db"))
    fallback_json_path: Path = Field(default=Path(".mgi_storage/local_memories.json"))
    collection_name: str = "mgi_agent_memories"
    default_user_id: str = Field(
        default_factory=lambda: os.environ.get("MGI_USER_ID", "local_developer")
    )
    default_agent_id: str = Field(
        default_factory=lambda: os.environ.get("MGI_AGENT_ID", "mgi_workspace_agent")
    )

    def to_mem0_dict(
        self, workspace_root: Path, llm: LLMProviderConfig, embedder: EmbedderConfig
    ) -> dict[str, Any]:
        """Convert to the native configuration dictionary expected by `mem0.Memory.from_config`."""
        qdrant_dir = (workspace_root / self.qdrant_path).resolve()
        history_db = (workspace_root / self.history_db_path).resolve()
        qdrant_dir.mkdir(parents=True, exist_ok=True)
        history_db.parent.mkdir(parents=True, exist_ok=True)

        llm_cfg: dict[str, Any] = {
            "model": llm.model,
            "temperature": llm.temperature,
            "max_tokens": llm.max_tokens,
        }
        if llm.provider == "ollama" and llm.base_url:
            llm_cfg["ollama_base_url"] = llm.base_url

        embed_cfg: dict[str, Any] = {
            "model": embedder.model,
            "embedding_dims": embedder.dims,
        }
        if embedder.provider == "ollama" and embedder.base_url:
            embed_cfg["ollama_base_url"] = embedder.base_url

        return {
            "vector_store": {
                "provider": self.vector_provider,
                "config": {
                    "collection_name": self.collection_name,
                    "path": str(qdrant_dir),
                    "embedding_model_dims": embedder.dims,
                },
            },
            "llm": {
                "provider": "ollama" if llm.provider == "litellm" else llm.provider,
                "config": llm_cfg,
            },
            "embedder": {
                "provider": embedder.provider,
                "config": embed_cfg,
            },
            "history_db_path": str(history_db),
            "version": "v1.1",
        }


class GraphifyConfig(BaseModel):
    """Configuration for Graphify AST & knowledge graph indexing and querying."""

    output_dir: Path = Field(default=Path("graphify-out"))
    graph_json_name: str = "graph.json"
    report_md_name: str = "GRAPH_REPORT.md"
    html_name: str = "graph.html"
    max_subgraph_nodes: int = 40
    default_bfs_depth: int = 2

    def graph_json_path(self, workspace_root: Path) -> Path:
        return (workspace_root / self.output_dir / self.graph_json_name).resolve()

    def report_md_path(self, workspace_root: Path) -> Path:
        return (workspace_root / self.output_dir / self.report_md_name).resolve()


class ICMConfig(BaseModel):
    """Configuration for Interpretable Context Methodology (5-Layer Hierarchy)."""

    default_max_context_tokens: int = 6000
    min_context_tokens: int = 2000
    max_stage_contract_lines: int = 80
    state_file: Path = Field(default=Path(".mgi_storage/icm_state.json"))
    chars_per_token: int = 4  # Fast deterministic token estimation ratio


class MGIConfig(BaseModel):
    """Root configuration for the `mem-graph-icm` stack."""

    workspace_root: Path = Field(default_factory=Path.cwd)
    llm: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    mem0: Mem0StorageConfig = Field(default_factory=Mem0StorageConfig)
    graphify: GraphifyConfig = Field(default_factory=GraphifyConfig)
    icm: ICMConfig = Field(default_factory=ICMConfig)


def get_config(workspace_root: Path | str | None = None) -> MGIConfig:
    root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
    return MGIConfig(workspace_root=root)
