from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mem_graph_icm.config import MGIConfig
from mem_graph_icm.icm.parser import StageContract


class ValidationReport(BaseModel):
    stage_id: str
    passed: bool
    created_outputs: list[Path] = Field(default_factory=list)
    missing_outputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    requires_hitl_approval: bool = False


class ICMQualityValidator:
    """
    Validates both pre-stage ICM contract discipline (e.g., <80 lines rule) and
    post-stage Quality Gates (`## 3. Outputs` and `## 4. Quality Gates & Checkpoints`).
    """

    def __init__(self, config: MGIConfig) -> None:
        self.config = config

    def validate_stage_outputs(self, stage: StageContract) -> ValidationReport:
        created: list[Path] = []
        missing: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        # 1. Check ICM contract length guideline (<80 non-empty lines)
        if stage.line_count > self.config.icm.max_stage_contract_lines:
            warnings.append(
                f"Stage contract `{stage.contract_path.name}` has {stage.line_count} lines "
                f"(ICM recommends <= {self.config.icm.max_stage_contract_lines} lines)."
            )

        # 2. Verify all expected outputs declared in `## 3. Outputs` exist and are non-empty
        for rel_out in stage.expected_output_paths:
            out_path = (stage.stage_dir / rel_out).resolve()
            if out_path.exists() and out_path.is_file():
                if out_path.stat().st_size == 0:
                    errors.append(f"Expected output `{rel_out}` is empty (0 bytes).")
                else:
                    created.append(out_path)
            else:
                missing.append(rel_out)
                errors.append(f"Missing required stage output artifact: `{rel_out}`.")

        # Also collect any files written to `stage_dir / "output"` if none were explicitly backticked
        default_out_dir = stage.stage_dir / "output"
        if default_out_dir.exists():
            for child in sorted(default_out_dir.rglob("*")):
                if child.is_file() and child not in created:
                    created.append(child)

        passed = len(errors) == 0
        return ValidationReport(
            stage_id=stage.stage_id,
            passed=passed,
            created_outputs=created,
            missing_outputs=missing,
            warnings=warnings,
            errors=errors,
            requires_hitl_approval=stage.hitl_checkpoint,
        )
