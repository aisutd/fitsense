"""Username/password sign-up and login (testing only - no sessions or tokens yet).

Login returns the user's id; the other endpoints are still addressed by user id
and don't check who is calling.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client

from app.database import get_supabase
from app.passwords import DUMMY_HASH, hash_password, verify_password
from app.schemas import AccountOut, LoginIn, SignupIn

router = APIRouter(prefix="/auth", tags=["auth"])

UNIQUE_VIOLATION = "23505"
BAD_LOGIN = HTTPException(status_code=401, detail="Wrong username or password")


def _has_profile(supabase: Client, user_id: str) -> bool:
    return bool(supabase.table("profiles").select("user_id").eq("user_id", user_id).limit(1).execute().data)


@router.post("/signup", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, supabase: Client = Depends(get_supabase)):
    """Create an account. The returned user_id is used for the profile created during onboarding."""
    row = {"username": body.username.lower(), "password_hash": hash_password(body.password)}
    try:
        account = supabase.table("accounts").insert(row).execute().data[0]
    except APIError as e:
        if e.code == UNIQUE_VIOLATION:
            raise HTTPException(status_code=409, detail="That username is taken")
        raise HTTPException(status_code=502, detail=f"Failed to create account: {e.message}")
    return {"user_id": account["user_id"], "username": account["username"], "has_profile": False}


@router.post("/login", response_model=AccountOut)
def login(body: LoginIn, supabase: Client = Depends(get_supabase)):
    try:
        found = (
            supabase.table("accounts").select("user_id, username, password_hash")
            .eq("username", body.username.strip().lower()).limit(1).execute().data
        )
        account = found[0] if found else None
        # Check a hash even for unknown usernames so timing doesn't reveal which exist.
        if not verify_password(body.password, account["password_hash"] if account else DUMMY_HASH) or not account:
            raise BAD_LOGIN
        supabase.table("accounts").update({"last_login_at": datetime.now(timezone.utc).isoformat()}).eq(
            "user_id", account["user_id"]
        ).execute()
        return {
            "user_id": account["user_id"],
            "username": account["username"],
            "has_profile": _has_profile(supabase, account["user_id"]),
        }
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to log in: {e.message}")
