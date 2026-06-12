import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models.product_card import ProductCard, CardStatus, IdempotencyKey
from app.core.config import settings

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

HEADERS = {"X-Service-Key": settings.SERVICE_KEY}

@pytest.fixture(autouse=True)
def clear_db():
    """Очищает БД перед каждым тестом"""
    db = TestingSessionLocal()
    try:
        db.query(ProductCard).delete()
        db.query(IdempotencyKey).delete()
        db.commit()
        yield
    finally:
        db.close()

def test_created_pending():
    """Событие CREATED создаёт карточку в PENDING"""
    payload = {
        "event": "CREATED",
        "product_id": "prod_001",
        "idempotency_key": "idem_001",
        "seller_id": "seller_001",
        "name": "Test Product",
        "description": "Test Description",
        "price": 99.99,
        "category": "electronics"
    }
    
    response = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response.status_code == 202
    
    db = TestingSessionLocal()
    card = db.query(ProductCard).filter(ProductCard.product_id == "prod_001").first()
    assert card is not None
    assert card.status == CardStatus.PENDING
    assert card.name == "Test Product"
    db.close()

def test_edited_returns_to_review():
    """EDITED после MODERATED/BLOCKED возвращает карточку в PENDING"""
    db = TestingSessionLocal()
    card = ProductCard(
        id="card_001",
        product_id="prod_002",
        seller_id="seller_002",
        name="Old Name",
        status=CardStatus.MODERATED
    )
    db.add(card)
    db.commit()
    db.close()
    
    payload = {
        "event": "EDITED",
        "product_id": "prod_002",
        "idempotency_key": "idem_002",
        "seller_id": "seller_002",
        "name": "New Name"
    }
    
    response = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response.status_code == 202
    
    db = TestingSessionLocal()
    card = db.query(ProductCard).filter(ProductCard.product_id == "prod_002").first()
    assert card.status == CardStatus.PENDING
    assert card.name == "New Name"
    db.close()

def test_edited_updates_in_review():
    """EDITED во время IN_REVIEW обновляет поля и возвращает в PENDING"""
    db = TestingSessionLocal()
    card = ProductCard(
        id="card_003",
        product_id="prod_003",
        seller_id="seller_003",
        name="Original",
        status=CardStatus.IN_REVIEW
    )
    db.add(card)
    db.commit()
    db.close()
    
    payload = {
        "event": "EDITED",
        "product_id": "prod_003",
        "idempotency_key": "idem_003",
        "seller_id": "seller_003",
        "name": "Updated"
    }
    
    response = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response.status_code == 202
    
    db = TestingSessionLocal()
    card = db.query(ProductCard).filter(ProductCard.product_id == "prod_003").first()
    assert card.status == CardStatus.PENDING
    assert card.name == "Updated"
    db.close()

def test_deleted_archived():
    """DELETED уводит карточку из очереди в ARCHIVED"""
    db = TestingSessionLocal()
    card = ProductCard(
        id="card_004",
        product_id="prod_004",
        seller_id="seller_004",
        status=CardStatus.PENDING
    )
    db.add(card)
    db.commit()
    db.close()
    
    payload = {
        "event": "DELETED",
        "product_id": "prod_004",
        "idempotency_key": "idem_004",
        "seller_id": "seller_004"
    }
    
    response = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response.status_code == 202
    
    db = TestingSessionLocal()
    card = db.query(ProductCard).filter(ProductCard.product_id == "prod_004").first()
    assert card.status == CardStatus.ARCHIVED
    db.close()

def test_duplicate_event_no_side_effects():
    """Повторное событие с тем же ключом идемпотентности → 202 без побочных эффектов"""
    payload = {
        "event": "CREATED",
        "product_id": "prod_005",
        "idempotency_key": "idem_005",
        "seller_id": "seller_005",
        "name": "Product"
    }
    
    # Первый запрос
    response1 = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response1.status_code == 202
    
    db = TestingSessionLocal()
    count_before = db.query(ProductCard).count()
    db.close()
    
    # Повторный запрос
    response2 = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response2.status_code == 202
    
    db = TestingSessionLocal()
    count_after = db.query(ProductCard).count()
    assert count_before == count_after  # Нет дублирования
    db.close()

def test_missing_service_header_401():
    """Запрос без межсервисного заголовка → 401"""
    payload = {
        "event": "CREATED",
        "product_id": "prod_006",
        "idempotency_key": "idem_006",
        "seller_id": "seller_006"
    }
    
    response = client.post("/api/v1/b2b/events", json=payload)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"

def test_hard_blocked_ignored():
    """События на HARD_BLOCKED карточку игнорируются"""
    db = TestingSessionLocal()
    card = ProductCard(
        id="card_007",
        product_id="prod_007",
        seller_id="seller_007",
        status=CardStatus.HARD_BLOCKED,
        name="Blocked"
    )
    db.add(card)
    db.commit()
    db.close()
    
    payload = {
        "event": "EDITED",
        "product_id": "prod_007",
        "idempotency_key": "idem_007",
        "seller_id": "seller_007",
        "name": "Should Not Update"
    }
    
    response = client.post("/api/v1/b2b/events", json=payload, headers=HEADERS)
    assert response.status_code == 202
    
    db = TestingSessionLocal()
    card = db.query(ProductCard).filter(ProductCard.product_id == "prod_007").first()
    assert card.name == "Blocked"  # Не обновилось
    db.close()