"""HTTP client for the Hadrian3 REST API.

The only hard dependency is ``httpx``. ``pandas`` is intentionally *not*
imported anywhere in this library (see docs/DECISIONS.md, "Client library has
no pandas dependency"): ``bulk_import``
duck-types the DataFrame via its ``.to_csv`` method, so callers who already
have pandas can pass a DataFrame while everyone else can pass ``str``/``bytes``/
``Path``.
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any

import httpx

__all__ = ["Client", "Hadrian3ClientError"]


class Hadrian3ClientError(Exception):
    """Raised when the API returns a non-2xx response.

    Exposes the HTTP ``status_code`` and the API ``detail`` message (as parsed
    from the JSON body's ``detail`` field, falling back to the raw text).
    """

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


def _isoformat(value: Any) -> Any:
    """Serialise datetime/date objects to ISO-8601 strings, pass through rest."""
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return value


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` without keys whose value is ``None``."""
    return {k: v for k, v in data.items() if v is not None}


class Client:
    """Thin synchronous client around the Hadrian3 REST API.

    Parameters
    ----------
    api_url:
        Base URL of the API (no trailing slash needed).
    timeout:
        Per-request timeout in seconds.
    http_client:
        Optional pre-built ``httpx.Client`` to inject. Useful for tests
        (``httpx.MockTransport``) and E2E (``httpx.ASGITransport`` against the
        FastAPI app). When provided, ``timeout`` is ignored and the caller owns
        the client's lifecycle.
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000",
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self._owns_client = http_client is None
        self._http = http_client if http_client is not None else httpx.Client(timeout=timeout)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Close the underlying httpx client if we created it."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- helpers -----------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    def _handle(self, res: httpx.Response) -> dict[str, Any]:
        if res.is_success:
            return res.json()
        detail: str
        try:
            body = res.json()
            detail = body.get("detail", res.text) if isinstance(body, dict) else res.text
        except Exception:
            detail = res.text
        raise Hadrian3ClientError(res.status_code, detail)

    # -- endpoints ---------------------------------------------------------

    def create_system(
        self,
        name: str,
        *,
        entry_rule: str | None = None,
        sl_rule: str | None = None,
        tp_rule: str | None = None,
        notes: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Create or upsert a system (POST /systems, idempotent by name).

        Only non-``None`` fields are sent. Returns the parsed JSON body.
        """
        payload = _drop_none(
            {
                "name": name,
                "entry_rule": entry_rule,
                "sl_rule": sl_rule,
                "tp_rule": tp_rule,
                "notes": notes,
                "status": status,
            }
        )
        res = self._http.post(self._url("/systems"), json=payload)
        return self._handle(res)

    def log_trade(
        self,
        *,
        system_name: str | None = None,
        system_id: int | None = None,
        r_value: float | None = None,
        trade_datetime: _dt.datetime | _dt.date | str | None = None,
        direction: str | None = None,
        entry: float | None = None,
        sl: float | None = None,
        exit: float | None = None,
        zone: str | None = None,
        timeframe: str | None = None,
        win_loss: str | None = None,
    ) -> dict[str, Any]:
        """Append a single trade (POST /trades, source is 'auto' server-side).

        ``system_id`` XOR ``system_name`` identifies the system. ``datetime``/
        ``date`` objects for ``trade_datetime`` are serialised via ``isoformat``.
        Only non-``None`` fields are sent. This endpoint is append-only (D2);
        for idempotent replacement use :meth:`bulk_import`.
        """
        payload = _drop_none(
            {
                "system_name": system_name,
                "system_id": system_id,
                "r_value": r_value,
                "trade_datetime": _isoformat(trade_datetime),
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "exit": exit,
                "zone": zone,
                "timeframe": timeframe,
                "win_loss": win_loss,
            }
        )
        res = self._http.post(self._url("/trades"), json=payload)
        return self._handle(res)

    def bulk_import(
        self,
        df: Any,
        system_name: str,
        replace: bool = True,
    ) -> dict[str, Any]:
        """Bulk-import trades from CSV (POST /import/csv, multipart).

        The ``df`` argument is duck-typed to avoid a hard pandas dependency (D4):

        * object with a ``.to_csv`` method (e.g. a pandas ``DataFrame``):
          ``df.to_csv(index=False)`` is called; a returned ``str`` is used
          directly and any other return value is read as text.
        * ``bytes``: used verbatim as the CSV payload.
        * ``str`` or ``os.PathLike``: if it points to an existing file, the file
          is read; otherwise the string itself is treated as raw CSV content.

        ``replace=True`` (default) is the idempotent path: it first deletes all
        ``source='auto'`` trades of the system before inserting (D2). Returns
        the parsed ImportRunResponse JSON.
        """
        csv_bytes = self._to_csv_bytes(df)
        files = {"file": ("trades.csv", csv_bytes, "text/csv")}
        data = {
            "system_name": system_name,
            "replace": "true" if replace else "false",
        }
        res = self._http.post(self._url("/import/csv"), files=files, data=data)
        return self._handle(res)

    @staticmethod
    def _to_csv_bytes(df: Any) -> bytes:
        # DataFrame-like: duck-type on .to_csv (no pandas import here).
        if hasattr(df, "to_csv"):
            out = df.to_csv(index=False)
            if isinstance(out, str):
                return out.encode("utf-8")
            if isinstance(out, bytes):
                return out
            # e.g. an io.StringIO/other file-like returned when path=None
            # is not passed; read whatever text it holds.
            return str(out).encode("utf-8")
        if isinstance(df, bytes):
            return df
        if isinstance(df, (str, os.PathLike)):
            p = Path(df)
            try:
                is_file = p.is_file()
            except OSError:
                is_file = False
            if is_file:
                return p.read_bytes()
            # Not an existing path -> treat the string as raw CSV content.
            return str(df).encode("utf-8")
        raise TypeError(
            "bulk_import expects a DataFrame-like (.to_csv), bytes, str CSV "
            f"content or a file path; got {type(df).__name__}"
        )
