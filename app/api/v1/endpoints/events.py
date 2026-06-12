from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.event import ProductEvent
from app.services.product_service import ProductService
from app.core.config import settings

router = APIRouter()


@router.post("/b2b/events", status_code=status.HTTP_202_ACCEPTED)
async def receive_product_event(
    event: ProductEvent,
    db: Session = Depends(get_db),
    x_service_key: str = Header(None, alias="X-Service-Key")
):
    """
    Принимает события о товарах от B2B сервиса.
    
    Поддерживаемые события:
    - CREATED: создание новой карточки товара (статус PENDING)
    - EDITED: редактирование карточки (возврат в PENDING)
    - DELETED: удаление карточки (статус ARCHIVED)
    
    Headers:
    - X-Service-Key: ключ межсервисной авторизации
    
    Returns:
    - 202: событие принято в обработку
    - 401: неверный или отсутствующий X-Service-Key
    - 400: невалидные данные события
    - 404: товар не найден (для EDITED)
    """
    # Проверка межсервисной авторизации
    if not x_service_key or x_service_key != settings.SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing or invalid X-Service-Key header"
            }
        )
    
    service = ProductService(db)
    service.process_event(event)
    
    return {"status": "accepted"}