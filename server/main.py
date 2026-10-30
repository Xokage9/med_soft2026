from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .db import init_db
from .routers import accounts, audit_api, auth, diagnoses, patients, staff
from .settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MedSoft HIS API", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.client_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


_FIELD_RU = {
    "last_name": "Фамилия", "first_name": "Имя", "middle_name": "Отчество", "position": "Должность",
    "role": "Роль", "birth_date": "Дата рождения", "sex": "Пол", "comment": "Комментарий",
    "code": "Код", "name": "Наименование", "username": "Логин", "password": "Пароль",
    "text": "Назначение", "operations": "Операции",
}


def _ru_message(err: dict) -> str:
    t, ctx = err["type"], err.get("ctx") or {}
    return {
        "missing": "обязательное поле",
        "string_too_short": f"минимум {ctx.get('min_length')} симв.",
        "string_too_long": f"максимум {ctx.get('max_length')} симв.",
        "string_pattern_mismatch": "недопустимые символы",
        "date_from_datetime_parsing": "неверная дата",
        "date_parsing": "неверная дата",
        "enum": "недопустимое значение",
        "literal_error": "недопустимое значение",
        "uuid_parsing": "неверный идентификатор",
        "too_short": "список пуст",
    }.get(t, str(err.get("msg", "")).removeprefix("Value error, "))


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        loc = [str(x) for x in e["loc"] if x not in ("body", "query", "path")]
        field = loc[-1] if loc else ""
        errors.append({"field": field, "message": _ru_message(e)})
    detail = "; ".join(f"{_FIELD_RU.get(e['field'], e['field'])}: {e['message']}" for e in errors)
    return JSONResponse(status_code=422, content={"detail": detail, "errors": errors})


@app.exception_handler(IntegrityError)
async def integrity_handler(_request: Request, _exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Нарушено ограничение целостности данных"})


for r in (auth.router, staff.router, accounts.router, diagnoses.router, audit_api.router,
          patients.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}
