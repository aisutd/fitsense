from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import Client

from app.database import get_supabase
from app.routers import profiles

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/test-supabase")
def test_supabase(supabase: Client = Depends(get_supabase)):
    response = (
        supabase
        .table("backend_test")
        .insert({"message": "Hello from FastAPI"})
        .execute()
    )

    return {"data": response.data}

@app.get("/test-supabase")
def read_supabase(supabase: Client = Depends(get_supabase)):
    response = (
        supabase
        .table("backend_test")
        .select("*")
        .execute()
    )

    return {"data": response.data}
