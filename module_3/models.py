import os
from sqlalchemy import create_engine, Column, Integer, Text, Float, Date
from sqlalchemy.orm import declarative_base, sessionmaker

# Base class that our ORM models will inherit from
Base = declarative_base()

class Applicant(Base):
    """
    Applicant model representing the applicants table in PostgreSQL.
    p_id is designated as the primary key.
    """
    __tablename__ = 'applicants'

    p_id = Column(Integer, primary_key=True)
    program = Column(Text, nullable=True)
    comments = Column(Text, nullable=True)
    date_added = Column(Date, nullable=True)
    url = Column(Text, nullable=True)
    status = Column(Text, nullable=True)
    term = Column(Text, nullable=True)
    us_or_international = Column(Text, nullable=True)
    gpa = Column(Float, nullable=True)
    gre = Column(Float, nullable=True)
    gre_v = Column(Float, nullable=True)
    gre_aw = Column(Float, nullable=True)
    degree = Column(Text, nullable=True)
    llm_generated_program = Column(Text, nullable=True)
    llm_generated_university = Column(Text, nullable=True)

# Read database URL from environment variable, falling back to local gradcafe database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost/gradcafe")

# Create the SQLAlchemy engine and session factory
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def get_db_session():
    """Returns a new database session for querying."""
    return SessionLocal()