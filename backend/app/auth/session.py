from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.auth.oidc import OIDCClient, OIDCError
from app.auth.rbac import get_active_roles, get_current_subject

router = APIRouter(prefix="/auth", tags=["auth"])
_TRANSACTION_KEY = "oidc_transaction"


def _oidc_client(request: Request) -> OIDCClient:
    return OIDCClient(request.app.state.settings)


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    client = _oidc_client(request)
    try:
        transaction = client.new_transaction()
        authorization_url = await client.authorization_url(transaction)
    except OIDCError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Institutional sign-in is temporarily unavailable.",
        ) from exc

    request.session.clear()
    request.session[_TRANSACTION_KEY] = transaction
    return RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    transaction = request.session.get(_TRANSACTION_KEY)
    request.session.clear()
    if (
        error is not None
        or not code
        or not state
        or not isinstance(transaction, dict)
        or not isinstance(transaction.get("state"), str)
        or not hmac.compare_digest(state, transaction["state"])
        or not all(isinstance(transaction.get(key), str) for key in ("nonce", "code_verifier"))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Institutional sign-in could not be completed.",
        )

    client = _oidc_client(request)
    try:
        tokens = await client.exchange_code(
            code=code,
            code_verifier=transaction["code_verifier"],
        )
        jwks = await client.get_signing_keys()
        claims = client.validate_token(
            tokens["id_token"],
            jwks,
            transaction["nonce"],
        )
    except OIDCError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Institutional sign-in could not be completed.",
        ) from exc

    subject = claims.get("sub")
    expires_at = claims.get("exp")
    if not isinstance(subject, str) or not isinstance(expires_at, (int, float)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Institutional sign-in could not be completed.",
        )

    request.session.clear()
    request.session.update({"sub": subject, "exp": expires_at})
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def current_reviewer(
    request: Request,
    subject: str = Depends(get_current_subject),
) -> dict[str, object]:
    roles = await get_active_roles(request.app, subject)
    return {
        "subject": subject,
        "roles": sorted(role.value for role in roles),
    }
