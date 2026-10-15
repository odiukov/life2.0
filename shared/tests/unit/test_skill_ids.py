from typing import get_args

from shared.analysis.personas import IDENTITY, VOCAB
from shared.skill_ids import Body, Calendar, Dashboard, Finance, FinanceSkillId, Home, HomeSkillId


def test_new_ids() -> None:
    assert (Dashboard.CARD, Dashboard.DETAIL) == ("dashboard.card", "dashboard.detail")
    assert get_args(FinanceSkillId) == (Finance.ASK,)
    assert get_args(HomeSkillId) == (Home.ASK,)
    assert Finance.IMPORT_STATEMENT == "finance.import_statement"
    assert Calendar.PROPOSE == "calendar.propose_change"
    assert Calendar.APPLY == "calendar.apply_change"
    assert Home.APPLY == "home.apply_action"
    assert Body.IMPORT_VIHEALTH == "body.import_vihealth"


def test_finance_has_an_identity() -> None:
    assert "finance" in IDENTITY["finance"].lower() or "money" in IDENTITY["finance"].lower()
    assert VOCAB["finance"].strip()
