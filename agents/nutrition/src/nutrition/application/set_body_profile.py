from __future__ import annotations

from pydantic import ValidationError
from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.domain.energy import BodyProfile
from shared.ports.llm import LLMError, LLMProvider, LLMTask
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory

from nutrition.application.ports import ProfileRepository
from nutrition.application.rendering import body_profile_saved
from nutrition.application.schemas import BodyProfileExtraction

BODY_PROFILE_SYSTEM = """Extract the body profile details the user states about themselves:
height in cm, age in years, sex (male or female), activity level (sedentary, light, moderate,
active, very_active) and a daily calorie goal in kcal. Return null for details not stated.
List a field in cleared_fields only when the user explicitly asks to clear that detail.
Null alone means no update; cleared_fields must be empty when no clear is requested."""

_FIELDS = tuple(name for name in BodyProfileExtraction.model_fields if name != "cleared_fields")


class SetBodyProfile:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        uow: UnitOfWorkFactory,
        translator: Translator,
        default_locale: str,
    ) -> None:
        self._llm = llm
        self._uow = uow
        self._tr = translator
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        async with self._uow.for_user(request.user_id) as uow:
            locale = (
                await uow.repo(ProfileRepository).get(request.user_id)
            ).locale or self._default_locale
        extracted: dict[str, object] = {}
        if request.text.strip():
            try:
                found = await self._llm.structured(
                    task=LLMTask.FAST,
                    system=BODY_PROFILE_SYSTEM,
                    user=request.text,
                    schema=BodyProfileExtraction,
                )
                extracted = {
                    key: value
                    for key, value in found.model_dump().items()
                    if key in _FIELDS and value is not None
                }
                extracted.update(dict.fromkeys(found.cleared_fields))
            except LLMError:
                extracted = {}
        explicit = {k: v for k, v in request.params.items() if k in _FIELDS}
        try:
            validated = BodyProfileExtraction.model_validate({**extracted, **explicit})
        except ValidationError as exc:
            names = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
            labels = ", ".join(
                self._tr.t(f"nutrition.body_profile.names.{n}", locale) for n in names
            )
            return SkillResult(
                output=self._tr.t("nutrition.body_profile.invalid", locale, fields=labels)
            )
        changes = validated.model_dump(exclude_unset=True, mode="json")
        if not changes:
            return SkillResult(output=self._tr.t("nutrition.body_profile.nothing_found", locale))
        async with self._uow.for_user(request.user_id) as uow:
            await uow.repo(ProfileRepository).update_body_profile(request.user_id, changes)
        saved = BodyProfile.from_mapping(changes)
        cleared = tuple(key for key, value in changes.items() if value is None)
        return SkillResult(
            output=body_profile_saved(saved, locale=locale, tr=self._tr, cleared_fields=cleared)
        )
