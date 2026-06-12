from sqlalchemy import Column, String, Float, Text, DateTime, Enum, JSON
from sqlalchemy.sql import func
from app.db.base_class import Base
import enum


class CardStatus(str, enum.Enum):
    """Статусы карточки товара в процессе модерации"""
    PENDING = "PENDING"           # Ожидает модерации
    IN_REVIEW = "IN_REVIEW"       # В процессе проверки модератором
    MODERATED = "MODERATED"       # Одобрена
    BLOCKED = "BLOCKED"           # Заблокирована (мягкая блокировка)
    HARD_BLOCKED = "HARD_BLOCKED" # Жёсткая блокировка (терминальный статус)
    ARCHIVED = "ARCHIVED"         # Архивирована (удалена)


class ProductCard(Base):
    """Карточка товара на модерации"""
    __tablename__ = "product_cards"

    id = Column(String, primary_key=True, index=True)
    product_id = Column(String, unique=True, nullable=False, index=True)
    seller_id = Column(String, nullable=False, index=True)
    
    # Данные товара
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    
    # Статус модерации
    status = Column(
        Enum(CardStatus),
        default=CardStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # ADR: храним json_before и json_after для диагностики инцидентов
    # Позволяет модератору видеть что изменилось и быстро диагностировать проблемы
    json_before = Column(JSON, nullable=True, comment="Состояние до изменения")
    json_after = Column(JSON, nullable=True, comment="Состояние после изменения")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class IdempotencyKey(Base):
    """Таблица для отслеживания обработанных событий (идемпотентность)"""
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True, index=True, comment="Ключ идемпотентности из события")
    product_id = Column(String, nullable=False, comment="ID товара, к которому относится событие")
    event_type = Column(String, nullable=True, comment="Тип события (CREATED/EDITED/DELETED)")
    processed_at = Column(DateTime(timezone=True), server_default=func.now())