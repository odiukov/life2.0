"""attention.items for medication: evening reminder for a regular medication."""

from __future__ import annotations

from datetime import date, timedelta

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork

from medication.application.ports import MedicationRepository
from medication.domain.attention import HISTORY_DAYS, MED_EVENING_HOUR, missed_today
from medication.domain.medication import Intake, Medication


def _matches(intake: Intake, med: Medication) -> bool:
    if intake.medication_id:
        return intake.medication_id == str(med.id)
    return intake.name.casefold() == med.name.casefold()


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    if ctx.now_local.hour < MED_EVENING_HOUR:
        return []
    meds = await tx.repo(MedicationRepository).active()
    if not meds:
        return []
    since, _ = ctx.bounds(ctx.today - timedelta(days=HISTORY_DAYS))
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["medication_taken"], since=since, agent="medication"
    )
    intakes = [Intake.from_row(r) for r in rows]
    items = []
    for med in meds:
        days: set[date] = {i.at.astimezone(ctx.zone).date() for i in intakes if _matches(i, med)}
        if missed_today(days, ctx.today):
            items.append(
                AttentionItem(
                    f"medication:missed:{med.id}:{ctx.today.isoformat()}",
                    "high",
                    -len(days),
                    ctx.t("attention.medication.missed", name=med.name),
                    AttentionAction("task", ctx.t("attention.medication.prompt", name=med.name)),
                    detail=ctx.t("attention.medication.missed_detail"),
                )
            )
    return items
