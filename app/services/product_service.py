from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.product_card import ProductCard, IdempotencyKey, CardStatus
from app.schemas.event import ProductEvent
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)


class ProductService:
    """Сервис обработки событий о товарах"""
    
    def __init__(self, db: Session):
        self.db = db

    def process_event(self, event: ProductEvent) -> None:
        """
        Обрабатывает входящее событие от B2B.
        
        Логика идемпотентности: если событие с таким ключом уже обработано,
        метод завершается без побочных эффектов.
        """
        # Проверка идемпотентности
        if self._is_duplicate(event.idempotency_key):
            logger.info(f"Duplicate event ignored: {event.idempotency_key}")
            return  # 202 без побочных эффектов
        
        # Обработка события в зависимости от типа
        if event.event == "CREATED":
            self._handle_created(event)
        elif event.event == "EDITED":
            self._handle_edited(event)
        elif event.event == "DELETED":
            self._handle_deleted(event)
        
        # Сохраняем ключ идемпотентности после успешной обработки
        self._save_idempotency_key(event.idempotency_key, event.product_id, event.event)
        
        logger.info(f"Event processed: {event.event} for product {event.product_id}")

    def _is_duplicate(self, idempotency_key: str) -> bool:
        """Проверяет, обрабатывалось ли это событие ранее"""
        return self.db.query(IdempotencyKey).filter(
            IdempotencyKey.key == idempotency_key
        ).first() is not None

    def _save_idempotency_key(self, key: str, product_id: str, event_type: str) -> None:
        """Сохраняет ключ идемпотентности в БД"""
        idem = IdempotencyKey(
            key=key,
            product_id=product_id,
            event_type=event_type
        )
        self.db.add(idem)
        self.db.commit()

    def _handle_created(self, event: ProductEvent) -> None:
        """
        Обрабатывает событие CREATED.
        
        Создаёт новую карточку товара в статусе PENDING.
        Если карточка уже существует и не в HARD_BLOCKED - ошибка.
        Если в HARD_BLOCKED - игнорируем (терминальный статус).
        """
        existing = self.db.query(ProductCard).filter(
            ProductCard.product_id == event.product_id
        ).first()
        
        if existing:
            # Терминальный статус - игнорируем
            if existing.status == CardStatus.HARD_BLOCKED:
                logger.warning(f"Product {event.product_id} is HARD_BLOCKED, ignoring CREATED event")
                return
            
            # Карточка уже существует - ошибка
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "DUPLICATE_PRODUCT",
                    "message": f"Product {event.product_id} already exists"
                }
            )
        
        json_after = self._event_to_json(event)
        
        card = ProductCard(
            id=str(uuid.uuid4()),
            product_id=event.product_id,
            seller_id=event.seller_id,
            name=event.name,
            description=event.description,
            price=event.price,
            category=event.category,
            status=CardStatus.PENDING,
            json_before=None,
            json_after=json_after
        )
        self.db.add(card)
        self.db.commit()
        
        logger.info(f"Created product card {card.id} for product {event.product_id}")

    def _handle_edited(self, event: ProductEvent) -> None:
        """
        Обрабатывает событие EDITED.
        
        Логика возврата в очередь:
        - IN_REVIEW -> PENDING (модератор должен увидеть изменения)
        - MODERATED/BLOCKED -> PENDING (повторная проверка)
        - HARD_BLOCKED -> игнорируем (терминальный статус)
        - PENDING -> обновляем данные, статус не меняем
        """
        card = self.db.query(ProductCard).filter(
            ProductCard.product_id == event.product_id
        ).first()
        
        if not card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "PRODUCT_NOT_FOUND",
                    "message": f"Product {event.product_id} not found"
                }
            )
        
        # Терминальный статус - игнорируем
        if card.status == CardStatus.HARD_BLOCKED:
            logger.warning(f"Product {event.product_id} is HARD_BLOCKED, ignoring EDITED event")
            return
        
        # Сохраняем состояние до изменения (для ADR: диагностика инцидентов)
        json_before = self._card_to_json(card)
        
        # Обновляем поля товара
        if event.name is not None:
            card.name = event.name
        if event.description is not None:
            card.description = event.description
        if event.price is not None:
            card.price = event.price
        if event.category is not None:
            card.category = event.category
        
        json_after = self._event_to_json(event)
        
        card.json_before = json_before
        card.json_after = json_after
        
        # Логика возврата в очередь
        if card.status in [CardStatus.IN_REVIEW, CardStatus.MODERATED, CardStatus.BLOCKED]:
            old_status = card.status
            card.status = CardStatus.PENDING
            logger.info(f"Product {event.product_id} status changed {old_status} -> PENDING")
        
        self.db.commit()
        
        logger.info(f"Updated product card for product {event.product_id}")

    def _handle_deleted(self, event: ProductEvent) -> None:
        """
        Обрабатывает событие DELETED.
        
        Переводит карточку в статус ARCHIVED.
        Если карточка не найдена - мягкая обработка (товар уже удалён).
        """
        card = self.db.query(ProductCard).filter(
            ProductCard.product_id == event.product_id
        ).first()
        
        if not card:
            # Мягкая обработка - товар уже удалён или не существовал
            logger.warning(f"Product {event.product_id} not found for DELETED event, ignoring")
            return
        
        # Сохраняем состояние перед архивацией
        card.json_before = self._card_to_json(card)
        card.status = CardStatus.ARCHIVED
        self.db.commit()
        
        logger.info(f"Archived product card for product {event.product_id}")

    def _event_to_json(self, event: ProductEvent) -> dict:
        """Конвертирует событие в JSON для хранения"""
        return {
            "product_id": event.product_id,
            "seller_id": event.seller_id,
            "name": event.name,
            "description": event.description,
            "price": event.price,
            "category": event.category,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None
        }

    def _card_to_json(self, card: ProductCard) -> dict:
        """Конвертирует карточку в JSON для хранения"""
        return {
            "product_id": card.product_id,
            "seller_id": card.seller_id,
            "name": card.name,
            "description": card.description,
            "price": card.price,
            "category": card.category,
            "status": card.status.value
        }