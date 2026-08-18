import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ai_benefit_desk.db.database import Base
from ai_benefit_desk.db.init_db import init_db

@pytest.fixture
def db_session():
    """Provide an in-memory SQLite database session for testing."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    init_db(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
