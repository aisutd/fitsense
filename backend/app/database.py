import os
from functools import lru_cache

from fastapi import HTTPException
from supabase import create_client, Client


@lru_cache
def _create_supabase(url: str, key: str) -> Client:
    return create_client(url, key)


def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Database not configured: set SUPABASE_URL and SUPABASE_KEY (see .env.example)",
        )
    return _create_supabase(url, key)
