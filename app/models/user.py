from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship
from typing import List, Optional


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    documents: List["Document"] = Relationship(back_populates="owner")
    versions: List["DocumentVersion"] = Relationship(back_populates="creator")
