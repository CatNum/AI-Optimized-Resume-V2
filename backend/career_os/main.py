from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from career_os.api.chat import router as chat_router
from career_os.api.sessions import router as sessions_router
from career_os.config import settings

app = FastAPI()

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(chat_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
