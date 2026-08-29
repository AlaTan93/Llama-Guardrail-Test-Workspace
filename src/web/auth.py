"""Bearer-token authentication for the web API.

Every ``/api`` route requires ``Authorization: Bearer <token>``.  The SSE
endpoint also accepts ``?token=<token>`` because ``EventSource`` cannot set
request headers.
"""

import secrets

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    token: str = getattr(request.app.state, "web_token", "")
    supplied = credentials.credentials if credentials else request.query_params.get("token", "")
    if not token or not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="invalid or missing token")
