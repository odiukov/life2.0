"""finance.import_statement: one Payoneer PDF in, new transactions stored and categorized."""

from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository

from finance.application.categorize import Categorizer
from finance.application.ports import PdfText, TransactionRepository, UnreadablePdf
from finance.application.summary import render_import_summary
from finance.domain.figures import Transaction, month_bounds, month_of
from finance.domain.statement import NotAStatement, parse_statement_text


def _fail(code: str) -> SkillResult:
    return SkillResult(output=code, failed=True)


class ImportStatement:
    def __init__(
        self,
        *,
        pdf: PdfText,
        uow: UnitOfWorkFactory,
        categorize: Categorizer,
        clock: Clock,
        translator: Translator,
        default_locale: str,
    ) -> None:
        self._pdf = pdf
        self._uow = uow
        self._categorize = categorize
        self._clock = clock
        self._tr = translator
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        if len(request.attachments) != 1:
            return _fail("invalid_params")
        upload = request.attachments[0]
        if upload.mime != "application/pdf":
            return _fail("invalid_params")
        try:
            parsed = parse_statement_text(self._pdf.extract(upload.data))
        except UnreadablePdf:
            return _fail("unreadable_pdf")
        except NotAStatement:
            return _fail("not_a_statement")
        uid = request.user_id
        ids = [r.txn_id for r in parsed.rows]
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
            repo = tx.repo(TransactionRepository)
            inserted = await repo.add_new(uid, parsed.rows)
            pending = await repo.uncategorized(uid, ids)
        locale = settings.locale or self._default_locale
        skipped = len(parsed.rows) - inserted + parsed.skipped
        if not parsed.rows:
            return SkillResult(
                output=self._tr.t("finance.import.empty", locale, skipped=parsed.skipped),
                data={"inserted": 0, "skipped": parsed.skipped, "months": []},
            )
        await self._categorize(uid, pending)  # outside any transaction: it may call the model
        months = sorted({month_of(r.ts, settings.timezone) for r in parsed.rows})
        rows: list[Transaction] = []
        async with self._uow.for_user(uid) as tx:
            for month in months:
                rows.extend(
                    await tx.repo(TransactionRepository).between(
                        uid, *month_bounds(month, settings.timezone)
                    )
                )
        summary = render_import_summary(
            self._tr, locale, inserted=inserted, skipped=skipped, rows=rows
        )
        return SkillResult(
            output=summary, data={"inserted": inserted, "skipped": skipped, "months": months}
        )
