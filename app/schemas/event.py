from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class ProductEvent(BaseModel):
    """Схема события о товаре от B2B сервиса"""
    
    event: Literal["CREATED", "EDITED", "DELETED"] = Field(
        ...,
        description="Тип события"
    )
    product_id: str = Field(
        ...,
        description="Уникальный идентификатор товара",
        min_length=1
    )
    idempotency_key: str = Field(
        ...,
        description="Ключ идемпотентности для защиты от дублирующих событий",
        min_length=1
    )
    seller_id: str = Field(
        ...,
        description="ID продавца",
        min_length=1
    )
    
    # Поля товара (опциональны для DELETED)
    name: Optional[str] = Field(None, description="Название товара")
    description: Optional[str] = Field(None, description="Описание товара")
    price: Optional[float] = Field(None, ge=0, description="Цена товара")
    category: Optional[str] = Field(None, description="Категория товара")
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Время события"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "event": "CREATED",
                    "product_id": "prod_123",
                    "idempotency_key": "idem_abc123",
                    "seller_id": "seller_456",
                    "name": "Gaming Laptop",
                    "description": "High-performance gaming laptop",
                    "price": 1299.99,
                    "category": "electronics",
                    "timestamp": "2024-01-01T12:00:00Z"
                },
                {
                    "event": "EDITED",
                    "product_id": "prod_123",
                    "idempotency_key": "idem_def456",
                    "seller_id": "seller_456",
                    "name": "Gaming Laptop Pro",
                    "price": 1399.99,
                    "timestamp": "2024-01-02T14:30:00Z"
                },
                {
                    "event": "DELETED",
                    "product_id": "prod_123",
                    "idempotency_key": "idem_ghi789",
                    "seller_id": "seller_456",
                    "timestamp": "2024-01-03T16:45:00Z"
                }
            ]
        }