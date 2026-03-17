from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CopyRiskSummary:
    warnings: list[str]
    confirmation_phrase: str


class CopyRiskService:
    def validate_scale_bps(self, scale_bps: int) -> None:
        if scale_bps < 500:
            raise ValueError("Scale must be at least 5%")
        if scale_bps > 30_000:
            raise ValueError("Scale must be at most 300%")

    def build_summary(
        self,
        *,
        source_display_name: str,
        scale_bps: int,
        notional_estimate: float,
        position_count: int,
    ) -> CopyRiskSummary:
        scale_pct = scale_bps / 100
        warnings = [
            f"You are authorizing live mirroring at {scale_pct:.2f}% of the source bot operator size.",
            f"Estimated copied exposure can reach about ${notional_estimate:,.2f} across {position_count} live positions.",
            "Execution may differ from the source due to slippage, liquidity, margin limits, or Pacifica latency.",
        ]
        phrase = f"COPY {source_display_name.upper()[:18]}"
        return CopyRiskSummary(warnings=warnings, confirmation_phrase=phrase)
