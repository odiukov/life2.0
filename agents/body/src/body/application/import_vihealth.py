"""body.import_vihealth: one ViHealth PDF → one body_composition row (+ optional profile fields)."""

from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.profile import BodyProfileRepository
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository

from body.application.ports import ReportReader, ReportVision, UnreadablePdf, VisionUnavailable
from body.domain.vihealth import (
    fallback_time,
    looks_like_vihealth,
    measured_at,
    metrics_from_tables,
    metrics_from_text,
    profile_from_text,
    row_data,
)

SAVED_PROFILE_KEYS = ("height_cm", "age", "sex")


def _fail(code: str) -> SkillResult:
    return SkillResult(output=code, failed=True)


class ImportViHealth:
    def __init__(
        self,
        *,
        reader: ReportReader,
        vision: ReportVision,
        uow: UnitOfWorkFactory,
        translator: Translator,
        default_locale: str,
    ) -> None:
        self._reader, self._vision, self._uow = reader, vision, uow
        self._tr, self._default_locale = translator, default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        if len(request.attachments) != 1 or request.attachments[0].mime != "application/pdf":
            return _fail("invalid_params")
        data = request.attachments[0].data
        try:
            text = self._reader.text(data)
            metrics = {**metrics_from_text(text), **metrics_from_tables(self._reader.tables(data))}
        except UnreadablePdf:
            return _fail("unreadable_pdf")
        when = measured_at(text)
        profile = profile_from_text(text)
        if not metrics:
            if text.strip() and not looks_like_vihealth(text):
                return _fail("not_a_report")
            try:
                png = self._reader.first_page_png(data)
                vision_time, metrics = await self._vision.metrics(png)
                when = vision_time or when
                profile = profile or await self._vision.profile(png)
            except UnreadablePdf:
                return _fail("unreadable_pdf")
            except VisionUnavailable:
                return _fail("vision_unavailable")
        values = row_data(metrics)
        if not values:
            return _fail("not_a_report")
        recorded = when or fallback_time(data)
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
            written = await tx.repo(HealthLogRepository).upsert(
                uid,
                HealthLogRow(
                    type="body_composition",
                    recorded_at=recorded,
                    data=values,
                    source="vihealth",
                    agent="body",
                ),
            )
            if request.params.get("save_profile") is True:
                changes = {k: profile[k] for k in SAVED_PROFILE_KEYS if k in profile}
                if changes:
                    await tx.repo(BodyProfileRepository).update(uid, changes)
        locale = settings.locale or self._default_locale
        return SkillResult(
            output=self._summary(locale, values, written),
            data={
                "profile_fields": profile,
                "written": int(written),
                "unchanged": int(not written),
                "recorded_at": recorded.isoformat(),
            },
        )

    def _summary(self, locale: str, values: dict[str, float], written: bool) -> str:
        parts = []
        if "weight_kg" in values:
            parts.append(self._tr.t("body.import.weight", locale, value=values["weight_kg"]))
        if "body_fat_pct" in values:
            parts.append(self._tr.t("body.import.fat", locale, value=values["body_fat_pct"]))
        if "bmi" in values:
            parts.append(self._tr.t("body.import.bmi", locale, value=values["bmi"]))
        detail = ", ".join(parts) + "." if parts else ""
        key = "body.import.written" if written else "body.import.unchanged"
        return "\n".join(line for line in (self._tr.t(key, locale, count=1), detail) if line)
