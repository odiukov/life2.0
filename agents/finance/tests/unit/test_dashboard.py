from finance.application.dashboard import detail
from finance.application.ports import TransactionRepository
from finance.domain.figures import Transaction
from finance.testing import InMemoryTransactions
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g


def transactions_repo() -> InMemoryTransactions:
    repo = InMemoryTransactions()
    repo.rows[g.USER_ID] = {
        str(r["txn_id"]): Transaction(
            str(r["txn_id"]),
            r["ts"],
            r["direction"],
            r["amount"],
            str(r["currency"]),
            str(r["description"]),
            r["category"],
        )  # type: ignore[arg-type]
        for r in g.transaction_rows()
    }
    return repo


async def test_detail_matches_the_golden() -> None:
    assert await g.golden_call(
        detail, Dashboard.DETAIL, {TransactionRepository: transactions_repo()}
    ) == g.expected_detail("finance")
