from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import concepts as concepts_api
from app.api import import_ as import_api
from app.api import live_settings as live_settings_api
from app.api import live_trades as live_trades_api
from app.api import quant as quant_api
from app.api import risk as risk_api
from app.api import risk_rules as risk_rules_api
from app.api import systems as systems_api
from app.api import trades as trades_api

app = FastAPI(title="Hadrian3 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    # Allow access via the WSL/LAN IP (NAT mode without localhost forwarding):
    # gleiche App, anderer Origin-Host — nur Port 3000 bleibt zugelassen.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


app.include_router(systems_api.router)
app.include_router(trades_api.router)
app.include_router(import_api.router)
app.include_router(concepts_api.router)
app.include_router(risk_rules_api.router)
app.include_router(quant_api.router)
app.include_router(risk_api.router)
app.include_router(live_trades_api.router)
app.include_router(live_settings_api.router)
