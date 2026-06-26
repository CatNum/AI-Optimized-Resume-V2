from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from career_os.api.chat import router as chat_router
from career_os.api.sessions import router as sessions_router
from career_os.config import settings
from career_os.platform.tool.handlers.outputs import canonical_output_prefix, resolve_output_file

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

_output_mount = Path(settings.output_dir).resolve()
if _output_mount.exists():
    app.mount(
        f"/{canonical_output_prefix()}",
        StaticFiles(directory=str(_output_mount)),
        name="output_static",
    )


@app.get("/v1/outputs/view")
def view_output(path: str):
    """view_output（view output）的函数说明。

    path（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    resolved = resolve_output_file(path)
    if resolved is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="output_not_found")
    return FileResponse(resolved, media_type="text/html; charset=utf-8")


@app.get("/healthz")
def healthz():
    """healthz（healthz）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return {"status": "ok"}
