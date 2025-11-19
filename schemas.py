"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

# --- App Schemas ---

class Attachment(BaseModel):
    filename: str
    url: str
    content_type: Optional[str] = None
    size: Optional[int] = None

class Activity(BaseModel):
    """
    Activities collection schema
    Collection name: "activity"
    """
    date: date = Field(..., description="Tanggal kegiatan")
    name: str = Field(..., description="Nama kegiatan")
    category: str = Field(..., description="Kategori kegiatan: administrasi, akademik, keuangan, sosial, P2M, dokumentasi")
    duration: float = Field(..., ge=0, description="Durasi (jam)")
    result: Optional[str] = Field(None, description="Hasil kegiatan")
    notes: Optional[str] = Field(None, description="Catatan tambahan")

    # Optional finance section
    income: Optional[float] = Field(0, ge=0, description="Pemasukan")
    expense: Optional[float] = Field(0, ge=0, description="Pengeluaran")
    finance_category: Optional[str] = Field(None, description="Kategori keuangan")

    attachments: List[Attachment] = Field(default_factory=list, description="Daftar file bukti")

# Example schemas kept for reference (not used by the app directly)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = Field(None, ge=0, le=120)
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
