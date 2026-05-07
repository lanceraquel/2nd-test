import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test_atlas_pipeline.db"
os.environ["REPORT_OUTPUT_DIR"] = "test_reports"

from app import models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
