from __future__ import annotations

from fastapi import HTTPException, Request

from huntly.context import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def require_unlocked(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    if not ctx.vault.unlocked:
        raise HTTPException(status_code=423, detail="Vault is locked. Unlock Huntly to continue.")
    return ctx
