class NoHousehold(Exception):
    """The actor has no household membership (should not happen behind the gateway hook)."""


class ItemGone(Exception):
    """The batch does not exist in this household or is no longer active."""


class InvalidAction(Exception):
    """The action is missing a required argument or the argument is out of range."""
