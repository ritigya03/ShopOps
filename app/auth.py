from functools import lru_cache

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel

from app.config import settings
from app.observability.context import user_id_var

_ROLE_PRIORITY = ["OperationsManager", "SupportAgent", "Viewer"]


class CurrentUser(BaseModel):
    sub: str
    email: str
    role: str


@lru_cache
def _jwks_client() -> PyJWKClient:
    issuer = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    return PyJWKClient(f"{issuer}/.well-known/jwks.json")


def _primary_role(groups: list[str]) -> str:
    for role in _ROLE_PRIORITY:
        if role in groups:
            return role
    raise jwt.InvalidTokenError("token has no recognized cognito:groups role")


def decode_cognito_token(token: str) -> CurrentUser:
    issuer = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token, signing_key.key, algorithms=["RS256"],
        audience=settings.cognito_app_client_id, issuer=issuer,
    )
    role = _primary_role(claims.get("cognito:groups", []))
    sub = claims.get("sub")
    if not sub:
        # Bare claims["sub"] would raise an uncaught KeyError here (not
        # jwt.InvalidTokenError), slipping past get_current_user's except
        # clause as an unhandled 500. Raising InvalidTokenError explicitly
        # keeps this failure mode inside the same caught family as every
        # other invalid-token case.
        raise jwt.InvalidTokenError("token is missing required 'sub' claim")
    return CurrentUser(sub=sub, email=claims.get("email", ""), role=role)


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    # Deliberately `async def`: FastAPI runs sync dependencies via
    # run_in_threadpool, which executes them in a *copied* context, so the
    # `user_id_var.set()` below would be discarded on return and every log
    # line for the request would carry `user_id: null`. An async dependency
    # runs on the event loop in the request's own context.
    # decode_cognito_token stays sync (the JWKS client is cached and fast
    # after the first call) and is called directly, not awaited.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        user = decode_cognito_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    user_id_var.set(user.sub)
    return user
