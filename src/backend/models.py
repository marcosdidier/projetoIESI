from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from sqlalchemy.orm import relationship

Base = declarative_base()

class Experiment(Base):
    __tablename__ = "experiments"
    id = Column(String, primary_key=True, index=True)
    researcher_id = Column(Integer, ForeignKey("researchers.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.now())
    researcher = relationship("Researcher", back_populates="experiments")

class Researcher(Base):
    __tablename__ = "researchers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now())
    experiments = relationship("Experiment", back_populates="researcher", cascade="all, delete-orphan")