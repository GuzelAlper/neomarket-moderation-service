from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.v1.endpoints import events
from app.db.session import engine
from app.db.base import Base

app = FastAPI(
    title="NeoMarket Moderation Service",
    description="Сервис модерации товаров для NeoMarket",
    version="1.0.0"
)

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Подключение роутеров
app.include_router(events.router, prefix="/api/v1", tags=["events"])


# Глобальный обработчик HTTPException
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "ERROR", "message": str(exc.detail)}
    )


# Глобальный обработчик ValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Invalid request data",
            "details": exc.errors()
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "moderation"}