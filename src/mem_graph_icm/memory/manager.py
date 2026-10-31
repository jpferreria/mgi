from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mem_graph_icm.config import MGIConfig


class MemoryRecord(BaseModel):
    """Normalized representation of a Mem0 memory item with Graphify & ICM metadata."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory: str
    user_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    score: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Mem0LocalManager:
    """
    Manages persistent agent memories via `mem0ai` (configured for local on-disk Qdrant +
    Ollama/LiteLLM by default) and automatically falls back to a deterministic local JSON/BM25-like
    store (`.mgi_storage/local_memories.json`) if the local embedding/LLM server is offline.

    Supports Graphify-anchored memories (`graph_nodes: list[str]`) and ICM stage scoping.
    """

    def __init__(self, config: MGIConfig, force_fallback: bool = False) -> None:
        self.config = config
        self.force_fallback = force_fallback
        self._mem0_instance: Any | None = None
        self._mem0_init_attempted = False

    @property
    def fallback_file(self) -> Path:
        path = (self.config.workspace_root / self.config.mem0.fallback_json_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _get_native_mem0(self) -> Any | None:
        if self.force_fallback or not self.config.mem0.enabled:
            return None
        if self._mem0_init_attempted:
            return self._mem0_instance

        self._mem0_init_attempted = True
        try:
            from mem0 import Memory  # type: ignore[import-untyped]

            cfg_dict = self.config.mem0.to_mem0_dict(
                workspace_root=self.config.workspace_root,
                llm=self.config.llm,
                embedder=self.config.embedder,
            )
            self._mem0_instance = Memory.from_config(cfg_dict)
        except Exception:
            self._mem0_instance = None
        return self._mem0_instance

    def add_memory(
        self,
        content: str,
        *,
        stage_id: str | None = None,
        graph_nodes: list[str] | None = None,
        scope: str = "project",
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """
        Store an episodic or semantic fact in Mem0, anchoring it to the active ICM `stage_id`
        and any relevant `graphify` node IDs.
        """
        uid = user_id or self.config.mem0.default_user_id
        aid = agent_id or self.config.mem0.default_agent_id
        metadata: dict[str, Any] = {
            "scope": scope,
            "stage_id": stage_id or "global",
            "graph_nodes": graph_nodes or [],
            **(extra_metadata or {}),
        }

        record = MemoryRecord(
            memory=content.strip(),
            user_id=uid,
            agent_id=aid,
            run_id=run_id,
            metadata=metadata,
        )

        # Always persist to deterministic local index so offline searches & tests succeed
        self._save_to_local_store(record)

        native = self._get_native_mem0()
        if native is not None:
            try:
                native.add(
                    messages=[{"role": "user", "content": content}],
                    user_id=uid,
                    agent_id=aid,
                    run_id=run_id,
                    metadata=metadata,
                )
            except Exception:
                pass

        return record

    def search_memories(
        self,
        query: str,
        *,
        top_k: int = 5,
        stage_id: str | None = None,
        graph_nodes: list[str] | None = None,
        scope: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[MemoryRecord]:
        """
        Retrieve the top-K relevant memories from Mem0 (or local store fallback), boosting
        memories that share Graphify node anchors (`graph_nodes`) or match the requested `scope`.
        """
        uid = user_id or self.config.mem0.default_user_id
        aid = agent_id or self.config.mem0.default_agent_id

        native = self._get_native_mem0()
        if native is not None:
            try:
                raw_res = native.search(
                    query=query,
                    user_id=uid,
                    agent_id=aid,
                    limit=top_k,
                )
                items = raw_res.get("results", raw_res) if isinstance(raw_res, dict) else raw_res
                if isinstance(items, list) and items:
                    parsed: list[MemoryRecord] = []
                    for item in items[:top_k]:
                        parsed.append(
                            MemoryRecord(
                                id=str(item.get("id", uuid.uuid4())),
                                memory=str(item.get("memory", item.get("text", ""))),
                                user_id=uid,
                                agent_id=aid,
                                score=float(item.get("score", 1.0)),
                                metadata=item.get("metadata", {}) or {},
                            )
                        )
                    return parsed
            except Exception:
                pass

        return self._search_local_store(
            query=query,
            top_k=top_k,
            stage_id=stage_id,
            graph_nodes=graph_nodes,
            scope=scope,
        )

    def get_all_memories(self, scope: str | None = None) -> list[MemoryRecord]:
        records = self._load_local_store()
        if scope:
            records = [r for r in records if r.metadata.get("scope") == scope]
        return records

    def _load_local_store(self) -> list[MemoryRecord]:
        if not self.fallback_file.exists():
            return []
        try:
            raw = json.loads(self.fallback_file.read_text(encoding="utf-8"))
            return [MemoryRecord.model_validate(item) for item in raw]
        except Exception:
            return []

    def _save_to_local_store(self, record: MemoryRecord) -> None:
        records = self._load_local_store()
        # Deduplicate identical memory strings within the same stage
        for idx, existing in enumerate(records):
            if (
                existing.memory.lower() == record.memory.lower()
                and existing.metadata.get("stage_id") == record.metadata.get("stage_id")
            ):
                records[idx] = record
                self.fallback_file.write_text(
                    json.dumps([r.model_dump() for r in records], indent=2),
                    encoding="utf-8",
                )
                return

        records.append(record)
        self.fallback_file.write_text(
            json.dumps([r.model_dump() for r in records], indent=2),
            encoding="utf-8",
        )

    def _search_local_store(
        self,
        query: str,
        top_k: int = 5,
        stage_id: str | None = None,
        graph_nodes: list[str] | None = None,
        scope: str | None = None,
    ) -> list[MemoryRecord]:
        records = self._load_local_store()
        if not records:
            return []

        query_terms = {
            t.lower() for t in query.replace(",", " ").replace(".", " ").split() if len(t) > 2
        }
        anchor_set = {g.lower() for g in (graph_nodes or [])}

        scored: list[MemoryRecord] = []
        for rec in records:
            if scope and rec.metadata.get("scope") != scope:
                continue

            text_lower = rec.memory.lower()
            term_hits = sum(1 for term in query_terms if term in text_lower)
            score = float(term_hits) / max(len(query_terms), 1)

            # Boost if anchored to overlapping Graphify nodes
            rec_nodes = {str(n).lower() for n in rec.metadata.get("graph_nodes", [])}
            if anchor_set and (anchor_set & rec_nodes):
                score += 1.5

            # Slight boost if from the same ICM stage or global scope
            if stage_id and rec.metadata.get("stage_id") == stage_id:
                score += 0.3
            if rec.metadata.get("scope") == "global":
                score += 0.25

            # Even if query is broad (e.g. "*"), return recent memories with baseline score
            if score > 0 or not query_terms or query.strip() == "*":
                rec_copy = rec.model_copy(update={"score": round(score + 0.1, 3)})
                scored.append(rec_copy)

        scored.sort(key=lambda r: (r.score, r.created_at), reverse=True)
        return scored[:top_k]
