# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
ocean_resources.ram_distributor -- RAM-Distributor und Modell-Runtime-Scheduler
================================================================================

Setzt das präzisierte Konzept vom 24.10.2026 (#1949, #2027, #2028, #2152, #2334,
#2419, #2441) um:
1. Anschlusskriterium mit Fähigkeitsmeldung (`ConsumerCapability`)
2. Prioritätsklassen nach Nutzernähe mit Vererbung (`UserProximity`)
3. Tray-Schalter als Tendenz (`TendencyMode`: `compute`, `balanced`, `ollama`)
4. Deterministische Fallbacks für Verlierer (`FallbackDecision`)
5. Hysterese-Schutz gegen Watchdog-Fehlalarme beim 27B-Kaltstart (#2419, Rückbau
   der `free_emergency_pages=0`-Zwischenlösung)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Optional

from .contracts import Hold, identity, instant, positive


class UserProximity(IntEnum):
    """Prioritätsklassen nach Nutzernähe (kleinerer Wert = näher am Nutzer)."""

    DIRECT_INTERACTIVE = 1      # Direkter Nutzerkontakt (GUI-Chat, Telegram, Konsole)
    DELEGATED_FOREGROUND = 2    # Vom Nutzerauftrag losgeschickter Subagent / Kettenschritt
    SCHEDULED_ROUTINE = 3       # Termin-/Routine-Job, verzahnter Review-Lauf
    AUTONOMOUS_BACKGROUND = 4   # Autonomer Dauerläufer (z. B. Buddha Always-On)


VALID_TENDENCIES = ("compute", "balanced", "ollama")
VALID_FALLBACK_ACTIONS = ("cloud_router", "smaller_local_model", "defer_with_checkpoint", "reject_hold")


@dataclass(frozen=True)
class ConsumerCapability:
    """Anschlusskriterium & Fähigkeitsmeldung eines RAM-/Modell-Verbrauchers."""

    consumer_id: str
    kind: str  # "model" | "compute" | "media"
    weights_ram_bytes: int
    kv_reserve_bytes: int = 0
    overhead_bytes: int = 0
    can_yield_at_turn_boundary: bool = True
    can_checkpoint: bool = True
    fallback_chain: tuple[str, ...] = ("cloud_router", "defer_with_checkpoint")

    def __post_init__(self) -> None:
        identity(self.consumer_id)
        if self.kind not in {"model", "compute", "media"}:
            raise ValueError(f"Unbekannte Verbraucherart: {self.kind!r}")
        if not positive(self.weights_ram_bytes):
            raise ValueError("weights_ram_bytes muss positiv sein")
        if self.kv_reserve_bytes < 0 or self.overhead_bytes < 0:
            raise ValueError("Reserve-Bytes dürfen nicht negativ sein")
        for fb in self.fallback_chain:
            if fb not in VALID_FALLBACK_ACTIONS:
                raise ValueError(f"Unbekannte Fallback-Aktion: {fb!r}")

    @property
    def total_required_bytes(self) -> int:
        return self.weights_ram_bytes + self.kv_reserve_bytes + self.overhead_bytes


@dataclass(frozen=True)
class DistributorRequest:
    """Anfrage an den gemeinsamen RAM-Distributor inkl. vererbter Nutzernähe."""

    request_id: str
    consumer_id: str
    proximity: UserProximity = UserProximity.AUTONOMOUS_BACKGROUND
    inherited_from_proximity: Optional[UserProximity] = None
    parent_request_id: Optional[str] = None
    submitted_at: float = 0.0

    def __post_init__(self) -> None:
        identity(self.request_id)
        identity(self.consumer_id)
        if not instant(self.submitted_at):
            raise ValueError("submitted_at muss endlich und >= 0 sein")

    @property
    def effective_proximity(self) -> UserProximity:
        """Kind-Aufträge erben die höhere Nutzernähe ihres Auslösers (max. Stufe 2)."""
        if self.inherited_from_proximity is None:
            return self.proximity
        inherited = (
            UserProximity.DELEGATED_FOREGROUND
            if self.inherited_from_proximity == UserProximity.DIRECT_INTERACTIVE
            else self.inherited_from_proximity
        )
        return UserProximity(min(int(self.proximity), int(inherited)))


@dataclass(frozen=True)
class WatchdogHysteresisPolicy:
    """Ersatz für die statische `free_emergency_pages=0`-Zwischenlösung (#2419).

    Verhindert, dass `memwatchdog` ein 27B-Modell während des Ladens oder einer
    kurzen KV-Spitze fälschlich entlädt, hält aber die echte Notbremse für
    Compute-PULL-Schranken (#2409) aktiv.
    """

    system_reserve_bytes: int = 5 * 1024**3          # 5 GiB Basisreserve
    emergency_floor_bytes: int = 512 * 1024**2       # 512 MiB harte Notgrenze
    cold_start_grace_seconds: float = 90.0           # Schutzfenster beim Modell-Laden
    sustained_pressure_seconds: float = 15.0         # Druckstufe muss anhalten

    def should_evict_model(
        self,
        *,
        available_ram_bytes: int,
        pressure: str,
        seconds_since_model_load: float,
        sustained_critical_seconds: float,
    ) -> tuple[bool, str]:
        if available_ram_bytes < self.emergency_floor_bytes and pressure == "critical":
            return True, "emergency_floor_breached_critical"
        if seconds_since_model_load < self.cold_start_grace_seconds and pressure != "critical":
            return False, "within_cold_start_grace_window"
        if pressure == "critical" and sustained_critical_seconds >= self.sustained_pressure_seconds:
            return True, "sustained_critical_memory_pressure"
        return False, "within_safe_operating_envelope"


@dataclass(frozen=True)
class FallbackDecision:
    request_id: str
    consumer_id: str
    admitted: bool
    action: str  # "admitted_local" | one of VALID_FALLBACK_ACTIONS
    reason: str
    effective_rank: tuple[int, int, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RAMDistributor:
    """Einziger Host-Scheduler für RAM-Fackel, Modell-Residenz und Compute-Jobs."""

    total_ram_bytes: int
    tendency: str = "balanced"
    watchdog_policy: WatchdogHysteresisPolicy = field(default_factory=WatchdogHysteresisPolicy)
    _consumers: dict[str, ConsumerCapability] = field(default_factory=dict)
    _resident_consumer_id: Optional[str] = None
    _resident_loaded_at: float = 0.0

    def __post_init__(self) -> None:
        if not positive(self.total_ram_bytes):
            raise ValueError("total_ram_bytes muss positiv sein")
        if self.tendency not in VALID_TENDENCIES:
            raise ValueError(f"Ungültige Tendenz: {self.tendency!r}")

    def set_tendency(self, tendency: str) -> None:
        if tendency not in VALID_TENDENCIES:
            raise ValueError(f"Ungültige Tendenz: {tendency!r}; erlaubt: {VALID_TENDENCIES}")
        self.tendency = tendency

    def register_consumer(self, capability: ConsumerCapability) -> None:
        self._consumers[capability.consumer_id] = capability

    def _tendency_bias(self, kind: str, proximity: UserProximity) -> int:
        # Direkter Nutzerbedarf (Stufe 1) wird nie durch die Tendenz benachteiligt
        if proximity == UserProximity.DIRECT_INTERACTIVE:
            return 0
        if self.tendency == "compute" and kind == "compute":
            return -1
        if self.tendency == "ollama" and kind == "model":
            return -1
        return 0

    def rank_request(self, req: DistributorRequest) -> tuple[int, int, float]:
        cap = self._consumers.get(req.consumer_id)
        if cap is None:
            raise Hold(f"Unbekannter Verbraucher: {req.consumer_id}")
        prox = req.effective_proximity
        bias = self._tendency_bias(cap.kind, prox)
        return (int(prox), bias, req.submitted_at)

    def evaluate(
        self,
        requests: list[DistributorRequest],
        *,
        available_ram_bytes: int,
        pressure: str = "normal",
        now: float = 0.0,
    ) -> list[FallbackDecision]:
        if not requests:
            return []
        ordered = sorted(requests, key=self.rank_request)
        decisions: list[FallbackDecision] = []
        remaining_ram = max(0, available_ram_bytes - self.watchdog_policy.system_reserve_bytes)
        winner_granted = False

        for req in ordered:
            cap = self._consumers[req.consumer_id]
            rank = self.rank_request(req)
            # Wenn das Modell bereits resident ist, zählt nur die KV-Reserve
            needed = (
                cap.kv_reserve_bytes
                if self._resident_consumer_id == req.consumer_id
                else cap.total_required_bytes
            )
            if not winner_granted and pressure != "critical" and remaining_ram >= needed:
                winner_granted = True
                remaining_ram -= needed
                if cap.kind == "model" and self._resident_consumer_id != req.consumer_id:
                    self._resident_consumer_id = req.consumer_id
                    self._resident_loaded_at = now
                decisions.append(
                    FallbackDecision(
                        request_id=req.request_id,
                        consumer_id=req.consumer_id,
                        admitted=True,
                        action="admitted_local",
                        reason="sufficient_ram_after_reserve",
                        effective_rank=rank,
                    )
                )
            else:
                fb_action = cap.fallback_chain[0] if cap.fallback_chain else "reject_hold"
                reason = (
                    "critical_memory_pressure"
                    if pressure == "critical"
                    else "preempted_or_insufficient_ram"
                )
                decisions.append(
                    FallbackDecision(
                        request_id=req.request_id,
                        consumer_id=req.consumer_id,
                        admitted=False,
                        action=fb_action,
                        reason=reason,
                        effective_rank=rank,
                    )
                )
        return decisions
