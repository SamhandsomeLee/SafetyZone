"""Acceptance-gated engine hot-swap for the running backend (#50).

Wraps ``detect.hotswap.EngineHotSwap`` so a candidate is promoted **only** when
``AcceptanceResult.allows_hotswap`` is true. Failure keeps the active engine;
``rollback()`` restores the previous commit when available.

API
---
::

    from jetson_update.hotswap import RuntimeHotswap, promote_if_accepted

    gate = RuntimeHotswap(engine_hotswap)
    result = gate.promote(candidate_path, acceptance=acceptance_result)
    if result.switched:
        ...
    gate.rollback()

Or with injectable acceptance (tests / CI)::

    result = gate.promote(
        candidate_path,
        acceptance_config=AcceptanceConfig(engine_path=candidate, ...),
        evaluate_fn=my_mock,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from detect.hotswap import EngineHotSwap
from jetson_update.acceptance import (
    AcceptanceConfig,
    AcceptanceResult,
    EvaluateFn,
    run_acceptance,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HotswapResult:
    """Outcome of a promote / rollback attempt."""

    switched: bool
    reason: str
    active_path: Path | None
    previous_path: Path | None = None
    acceptance: AcceptanceResult | None = None


class HotswapRejected(RuntimeError):
    """Raised when promote is refused (acceptance gate or missing engine)."""


class RuntimeHotswap:
    """Gate ``EngineHotSwap`` behind frozen-testset acceptance.

    The held ``EngineHotSwap`` is the live infer backend (or a test double).
    ``promote`` never calls ``commit`` unless ``allows_hotswap`` is true.
    """

    def __init__(self, engine: EngineHotSwap) -> None:
        self._engine = engine

    @property
    def engine(self) -> EngineHotSwap:
        return self._engine

    @property
    def active_path(self) -> Path | None:
        return self._engine.active_path

    @property
    def previous_path(self) -> Path | None:
        return self._engine.previous_path

    def promote(
        self,
        candidate_path: str | Path,
        *,
        acceptance: AcceptanceResult | None = None,
        acceptance_config: AcceptanceConfig | None = None,
        evaluate_fn: EvaluateFn | None = None,
        dry_run: bool = False,
        warmup_n: int = 3,
    ) -> HotswapResult:
        """Run (or reuse) acceptance; commit only when the gate allows.

        Parameters
        ----------
        candidate_path
            Candidate TensorRT ``.engine`` to prepare / warmup / commit.
        acceptance
            Precomputed gate result. When set, acceptance is not re-run.
        acceptance_config
            Used when ``acceptance`` is omitted; ``engine_path`` should match
            the candidate (or is overridden to ``candidate_path``).
        evaluate_fn
            Injectable evaluator for tests / CI without GPU.
        dry_run
            Passed to ``run_acceptance`` when computing the gate.
        warmup_n
            Warmup iterations before ``commit``.
        """
        path = Path(candidate_path)
        before = self._engine.active_path

        gate = acceptance
        if gate is None:
            cfg = acceptance_config
            if cfg is None:
                cfg = AcceptanceConfig(engine_path=path)
            elif Path(cfg.engine_path) != path:
                cfg = AcceptanceConfig(
                    engine_path=path,
                    testset_dir=cfg.testset_dir,
                    recall_threshold=cfg.recall_threshold,
                    iou_match=cfg.iou_match,
                    conf=cfg.conf,
                    nms_iou=cfg.nms_iou,
                    person_class_id=cfg.person_class_id,
                )
            gate = run_acceptance(cfg, evaluate_fn=evaluate_fn, dry_run=dry_run)

        if not gate.allows_hotswap:
            reason = f"acceptance rejected; keep active engine ({before}): {gate.reason}"
            logger.warning("%s", reason)
            return HotswapResult(
                switched=False,
                reason=reason,
                active_path=before,
                previous_path=self._engine.previous_path,
                acceptance=gate,
            )

        try:
            self._engine.prepare(path)
            self._engine.warmup_candidate(warmup_n)
            committed = self._engine.commit()
        except Exception as exc:  # noqa: BLE001 — surface as failed promote
            self._engine.discard_candidate()
            reason = f"hotswap prepare/warmup/commit failed; keep active: {exc}"
            logger.exception("%s", reason)
            return HotswapResult(
                switched=False,
                reason=reason,
                active_path=self._engine.active_path,
                previous_path=self._engine.previous_path,
                acceptance=gate,
            )

        reason = f"hotswap committed: {committed} (previous={before})"
        logger.info("%s", reason)
        return HotswapResult(
            switched=True,
            reason=reason,
            active_path=self._engine.active_path,
            previous_path=self._engine.previous_path,
            acceptance=gate,
        )

    def rollback(self) -> HotswapResult:
        """Restore the engine retained after the last successful commit."""
        before = self._engine.active_path
        ok = self._engine.rollback()
        if not ok:
            reason = "rollback unavailable (no previous engine retained)"
            logger.warning("%s", reason)
            return HotswapResult(
                switched=False,
                reason=reason,
                active_path=before,
                previous_path=None,
            )
        reason = f"rolled back to {self._engine.active_path} (was {before})"
        logger.info("%s", reason)
        return HotswapResult(
            switched=True,
            reason=reason,
            active_path=self._engine.active_path,
            previous_path=self._engine.previous_path,
        )


def promote_if_accepted(
    engine: EngineHotSwap,
    candidate_path: str | Path,
    *,
    acceptance: AcceptanceResult | None = None,
    acceptance_config: AcceptanceConfig | None = None,
    evaluate_fn: EvaluateFn | None = None,
    dry_run: bool = False,
    warmup_n: int = 3,
) -> HotswapResult:
    """Convenience: gate + promote on an existing ``EngineHotSwap``."""
    return RuntimeHotswap(engine).promote(
        candidate_path,
        acceptance=acceptance,
        acceptance_config=acceptance_config,
        evaluate_fn=evaluate_fn,
        dry_run=dry_run,
        warmup_n=warmup_n,
    )


def rollback(engine: EngineHotSwap) -> HotswapResult:
    """Convenience: rollback on an existing ``EngineHotSwap``."""
    return RuntimeHotswap(engine).rollback()


# Re-export for callers that only import this module.
__all__ = [
    "HotswapRejected",
    "HotswapResult",
    "RuntimeHotswap",
    "promote_if_accepted",
    "rollback",
]
