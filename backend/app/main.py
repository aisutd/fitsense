from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import supabase

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/test-supabase")
def test_supabase():
    response = (
        supabase
        .table("backend_test")
        .insert({"message": "Hello from FastAPI"})
        .execute()
    )

@app.get("/test-supabase")
def read_supabase():
    response = (
        supabase
        .table("backend_test")
        .select("*")
        .execute()
    )
    
    return {"data": response.data}