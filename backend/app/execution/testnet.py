"""Real orders against the Hyperliquid **testnet**, and nothing else.

Verification status — read this before trusting it
--------------------------------------------------
The order construction, the mode gating, the credential handling and the
request shape are covered by tests. The **signature has not been exercised
against the live testnet** in this build: doing so needs a funded testnet agent
wallet, which is the operator's to create and is deliberately not committed
anywhere. The signing scheme below is implemented from Hyperliquid's documented
L1-action format; if it is wrong, the venue will reject the order outright
rather than filling something unintended, which is the right way for this
particular thing to fail. Treat the first live testnet order as the acceptance
test, and see PROGRESS.md.

Why signing is an optional dependency
-------------------------------------
``eth-account`` and ``msgpack`` are imported inside :meth:`place`, not at module
scope, and they are not in ``requirements.txt``. A default install of this
system therefore has **no capability to sign a transaction at all** — not a
guard saying no, an absence. That is a stronger property than any check, and it
is why the import is where it is. Installing ``requirements-testnet.txt`` is a
deliberate act by someone who has decided to trade the testnet.

The signature domain is pinned to the testnet's ``source`` character. The
mainnet one is not a constant in this file, not a branch, and not derivable
from anything here.
"""

from __future__ import annotations

import os
import time

import httpx

from app.execution.mode import EXCHANGE_BASE_URLS, ExecutionMode, require_permitted
from app.execution.orders import OrderIntent, OrderReceipt, OrderRejected

__all__ = ["TestnetExecutor", "TestnetNotConfigured"]

#: Hyperliquid's phantom-agent source character for the test network. The
#: production character is deliberately absent from this file.
_TESTNET_SOURCE = "b"

#: Fixed by the venue's signing scheme; not a network id to be configured.
_SIGNING_CHAIN_ID = 1337
_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

_ENV_KEY = "HL_TESTNET_AGENT_KEY"


class TestnetNotConfigured(RuntimeError):
    """Testnet execution was asked for without the means to do it."""


class TestnetExecutor:
    """Places immediate-or-cancel limit orders on the Hyperliquid testnet."""

    mode = ExecutionMode.TESTNET

    def __init__(
        self,
        agent_key: str | None = None,
        *,
        client: httpx.Client | None = None,
        asset_index: dict[str, int] | None = None,
        timeout_s: float = 10.0,
        **_ignored,
    ) -> None:
        # Gate in the constructor as well as in build_executor: this class is
        # importable, and something that can sign should refuse to exist in a
        # mode that must not sign, not merely refuse to act.
        require_permitted(self.mode)

        self._base_url = EXCHANGE_BASE_URLS[self.mode]
        # Read from the environment, never from a default, a config file or a
        # generated wallet. A key this process did not have to be given is a
        # key someone else can also obtain.
        self._agent_key = agent_key if agent_key is not None else os.environ.get(_ENV_KEY, "")
        self._client = client
        self._owns_client = client is None
        self._timeout_s = timeout_s
        self._asset_index = dict(asset_index or {})

    # -- lifecycle ---------------------------------------------------------- #

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "TestnetExecutor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- placing ------------------------------------------------------------ #

    def place(self, intent: OrderIntent) -> OrderReceipt:
        require_permitted(self.mode)

        if not self._agent_key.strip():
            raise TestnetNotConfigured(
                f"{_ENV_KEY} is not set. Generate a throwaway testnet agent "
                "wallet, fund it from the testnet faucet, and put its key in "
                "your own .env — never in the repository."
            )

        signer, pack = _load_signing_dependencies()

        action = self._order_action(intent)
        nonce = int(time.time() * 1000)
        signature = _sign_l1_action(signer, pack, self._agent_key, action, nonce)

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None,
        }

        response = self._http().post(
            f"{self._base_url}/exchange", json=payload, timeout=self._timeout_s
        )
        return self._receipt(intent, response)

    def _order_action(self, intent: OrderIntent) -> dict:
        """The venue's order payload.

        Immediate-or-cancel rather than a market order: the size was computed
        against a specific price, and an order that cannot fill near that price
        should not fill at all. A resting order would be worse still — it would
        leave the system believing it is flat while an order sits on the book.
        """
        return {
            "type": "order",
            "orders": [
                {
                    "a": self._index_for(intent.asset),
                    "b": intent.is_buy,
                    "p": _format_number(intent.limit_price()),
                    "s": _format_number(intent.size),
                    "r": intent.reduce_only,
                    "t": {"limit": {"tif": "Ioc"}},
                    "c": None,
                }
            ],
            "grouping": "na",
        }

    def _index_for(self, asset: str) -> int:
        try:
            return self._asset_index[asset.upper()]
        except KeyError:
            raise OrderRejected(
                f"no venue asset index known for {asset!r}. Load the universe "
                "from the /info 'meta' endpoint and pass it as asset_index."
            ) from None

    def _receipt(self, intent: OrderIntent, response: httpx.Response) -> OrderReceipt:
        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.status_code >= 400:
            return OrderReceipt(
                client_id=intent.client_id,
                mode=self.mode,
                accepted=False,
                status="rejected",
                message=f"testnet returned HTTP {response.status_code}: {response.text[:300]}",
                raw_response=body if isinstance(body, dict) else None,
            )

        status = body.get("status") if isinstance(body, dict) else None
        if status != "ok":
            return OrderReceipt(
                client_id=intent.client_id,
                mode=self.mode,
                accepted=False,
                status="rejected",
                message=f"testnet refused the order: {body}",
                raw_response=body if isinstance(body, dict) else None,
            )

        filled, order_id, average = _read_statuses(body)
        return OrderReceipt(
            client_id=intent.client_id,
            mode=self.mode,
            accepted=True,
            venue_order_id=order_id,
            filled_size=filled,
            average_price=average,
            status="filled" if filled else "resting",
            message=None,
            raw_response=body,
        )


def _read_statuses(body: dict) -> tuple[float, str | None, float | None]:
    """Pull the fill out of the venue's nested response.

    Defensive throughout: a response shape that has drifted should degrade to
    "accepted, details unknown" rather than raise inside the executor, because
    by this point the order has already been sent and losing the receipt is
    worse than losing the detail.
    """
    try:
        statuses = body["response"]["data"]["statuses"]
    except (KeyError, TypeError):
        return 0.0, None, None

    for entry in statuses:
        if not isinstance(entry, dict):
            continue
        if "filled" in entry:
            filled = entry["filled"]
            return (
                float(filled.get("totalSz", 0) or 0),
                str(filled.get("oid")) if filled.get("oid") is not None else None,
                float(filled["avgPx"]) if filled.get("avgPx") is not None else None,
            )
        if "resting" in entry:
            resting = entry["resting"]
            return (
                0.0,
                str(resting.get("oid")) if resting.get("oid") is not None else None,
                None,
            )
    return 0.0, None, None


def _format_number(value: float) -> str:
    """The venue wants numbers as strings without exponent or trailing zeros.

    ``repr`` would render 1e-05 for a small BTC size, which the venue rejects.
    """
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text or "0"


def _load_signing_dependencies():
    """Import the signing stack, or explain how to get it.

    Deferred to call time on purpose — see the module docstring. A default
    install cannot sign because the libraries are not there, which is a
    stronger guarantee than a check that they are not used.
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        import msgpack
    except ImportError as exc:
        raise TestnetNotConfigured(
            "testnet signing needs eth-account and msgpack, which are not part "
            "of the default install — this system ships unable to sign anything. "
            "Install requirements-testnet.txt if you have decided to trade the "
            "testnet."
        ) from exc
    return (Account, encode_typed_data), msgpack


def _sign_l1_action(signer, msgpack_module, agent_key: str, action: dict, nonce: int) -> dict:
    """Sign a Hyperliquid L1 action for the test network.

    The action is msgpack-encoded, concatenated with the nonce and a
    vault-address marker, hashed, and that hash is signed as an EIP-712
    ``Agent`` message. See the module docstring for what has and has not been
    verified about this.
    """
    from eth_utils import keccak

    account_module, encode_typed_data = signer

    packed = msgpack_module.packb(action)
    # No vault: a single trailing zero byte. A vault address would be a 0x01
    # followed by the address, which this build does not construct.
    digest = keccak(packed + nonce.to_bytes(8, "big") + b"\x00")

    typed_data = {
        "domain": {
            "chainId": _SIGNING_CHAIN_ID,
            "name": "Exchange",
            "verifyingContract": _ZERO_ADDRESS,
            "version": "1",
        },
        "types": {
            "Agent": [
                {"name": "source", "type": "string"},
                {"name": "connectionId", "type": "bytes32"},
            ],
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
        },
        "primaryType": "Agent",
        "message": {"source": _TESTNET_SOURCE, "connectionId": digest},
    }

    signed = account_module.sign_message(
        encode_typed_data(full_message=typed_data),
        private_key=agent_key,
    )
    return {"r": _hex32(signed.r), "s": _hex32(signed.s), "v": signed.v}


def _hex32(value: int) -> str:
    return "0x" + format(value, "064x")
