from __future__ import annotations

from typing import ClassVar


class HouseholdError(Exception):
    code: ClassVar[str] = "household_error"


class InviteInvalid(HouseholdError):
    code = "invite_invalid"


class InviteOwnHousehold(HouseholdError):
    code = "invite_own"


class InviteRateLimited(HouseholdError):
    code = "invite_rate_limited"


class NotOwner(HouseholdError):
    code = "not_owner"


class SoleMember(HouseholdError):
    code = "household_sole_member"


class CannotRemoveSelf(HouseholdError):
    code = "cannot_remove_self"


class NotMember(HouseholdError):
    code = "not_member"


class NoHousehold(HouseholdError):
    code = "no_household"


class InvalidSettings(HouseholdError):
    code = "invalid_settings"
