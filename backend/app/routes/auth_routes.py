from fastapi import APIRouter, Body, Depends, Header

from backend.app.services import auth

router = APIRouter()


@router.get("/mode", summary="Demo mode (no users set up) or pilot mode (logins required for actions)")
def get_mode():
    return {"pilot_mode": auth.pilot_mode(), "roles": list(auth.ROLES),
            "note": ("Pilot mode: every action that changes data needs a logged-in user with the right role." if auth.pilot_mode()
                     else "Demo mode: no users are set up, so actions are not attributable to a person. Not for real decisions.")}


@router.post("/login", summary="Log in; returns a token for the Authorization header")
def post_login(username: str = Body(...), password: str = Body(...)):
    return auth.login(username, password)


@router.post("/logout", summary="Log out")
def post_logout(authorization: str | None = Header(None)):
    auth.logout((authorization or "").removeprefix("Bearer ").strip())
    return {"ok": True}


@router.get("/me", summary="The logged-in user")
def get_me(user: dict | None = Depends(auth.current_user)):
    return {"user": None if user is None else {k: user[k] for k in ("username", "full_name", "role")}}
