from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./illegal_dumping.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DumpingEventModel(Base):
    __tablename__ = "dumping_events"

    id = Column(Integer, primary_key=True, index=True)
    cctv_id = Column(String(50), index=True)
    detected_at = Column(DateTime, default=datetime.now)
    status = Column(String(20), default="UNCHECKED")  # UNCHECKED, CONFIRMED, FALSE_POSITIVE
    snapshot_path = Column(String(255))
    trash_type = Column(String(50))
    confidence = Column(Float)
    bbox_json = Column(Text)

# [수정] create_engine -> create_all로 변경
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()