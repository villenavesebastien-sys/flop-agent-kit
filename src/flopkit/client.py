"""FlopClient: the interface your agent will implement once the testnet is live.

Nothing here talks to a network yet: chain id, RPC, faucet and session APIs are not published.
The kit never holds keys - signing stays in your own tooling. A typical purchase loop:

    url_ok   = flopkit.verify.check_url(client.rpc_url).verdict == "OFFICIAL"
    decision = flopkit.guard.check(to=miner, amount=x, own=own, sender=me, daily_cap=cap, ledger=ledger)
    if url_ok and decision.allowed:
        sid = client.open_session(miner, x)       # you sign inside your implementation
        ledger.add(sid, x, "pending", miner=miner)
        ...
        ledger.add(sid, None, client.session_status(sid))
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class FlopClient(ABC):
    rpc_url: str = ""

    @abstractmethod
    def chain_id(self) -> str: ...

    @abstractmethod
    def faucet_claim(self, account: str) -> dict:
        """Claim from the OFFICIAL faucet only. Returns the receipt."""

    @abstractmethod
    def open_session(self, miner: str, amount) -> str:
        """Open (and pay for) an inference session. Returns its session id."""

    @abstractmethod
    def session_status(self, session_id: str) -> str:
        """One of: pending, settled, disputed, refunded."""

    @abstractmethod
    def session_receipts(self, account: str, since_ms: int | None = None) -> list[dict]:
        """Settled-session receipts for reconciliation with the local ledger."""


class NotLiveClient(FlopClient):
    """Placeholder that fails loudly until the official testnet details exist."""

    def _no(self, *_a, **_k):
        raise NotImplementedError("FLOP testnet endpoints are not published yet - nothing to call")

    chain_id = faucet_claim = open_session = session_status = session_receipts = _no
