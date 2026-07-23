"""Google OAuth routes.

Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and SESSION_SECRET in .env before
using these routes. The user profile is intentionally stored only in the
signed session for this project.
"""

from __future__ import annotations

import logging
import os

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
oauth = OAuth()

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login", name="auth_login")
async def login(request: Request):
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google OAuth 환경 변수가 설정되지 않았습니다.")
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        reason = error.description or error.error or "OAuth 인증 오류"
        raise HTTPException(
            status_code=400,
            detail=f"Google 로그인 인증에 실패했습니다. ({reason})",
        ) from error
    except Exception as error:
        logger.exception("Google OAuth token exchange failed")
        raise HTTPException(
            status_code=502,
            detail="Google 계정 정보를 확인하지 못했습니다. 잠시 후 다시 로그인해 주세요.",
        ) from error

    user_info = token.get("userinfo", {})
    email = str(user_info.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Google 계정 이메일을 확인할 수 없습니다.")
    request.session.clear()
    request.session["user"] = {
        "name": user_info.get("name") or email,
        "email": email,
        "picture": user_info.get("picture", ""),
    }
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout", name="auth_logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
