import os
from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Activity

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Utility to convert ObjectId and datetime for JSON

def serialize_doc(doc):
    if not doc:
        return doc
    if doc.get("_id") is not None:
        doc["id"] = str(doc.get("_id"))
        doc.pop("_id", None)
    # Convert datetime/date to isoformat strings
    for k, v in list(doc.items()):
        if isinstance(v, (datetime, date)):
            doc[k] = v.isoformat()
        if isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    new_list.append(serialize_doc(item))
                else:
                    new_list.append(item)
            doc[k] = new_list
    return doc

# Helper to safely create ObjectId without import errors at startup

def to_object_id(oid: str):
    try:
        from bson.objectid import ObjectId  # import here to avoid global import issues
        return ObjectId(oid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")

# Basic routes
@app.get("/")
def read_root():
    return {"message": "Monthly Report API Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "Unknown"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# Models for updates and filters
class ActivityUpdate(BaseModel):
    date: Optional[date] = None
    name: Optional[str] = None
    category: Optional[str] = None
    duration: Optional[float] = None
    result: Optional[str] = None
    notes: Optional[str] = None
    income: Optional[float] = None
    expense: Optional[float] = None
    finance_category: Optional[str] = None

# CRUD Endpoints for activities
@app.post("/api/activities")
async def create_activity(activity: Activity):
    try:
        new_id = create_document("activity", activity)
        return {"id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/activities")
async def list_activities(month: Optional[int] = None, year: Optional[int] = None, category: Optional[str] = None, search: Optional[str] = None):
    query = {}
    if month or year:
        try:
            y = year or datetime.utcnow().year
            m = month or datetime.utcnow().month
            start = datetime(y, m, 1)
            end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
            # Store/query using datetime for BSON compatibility
            query["date"] = {"$gte": start.date(), "$lt": end.date()}
        except Exception:
            pass
    if category:
        query["category"] = category
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"result": {"$regex": search, "$options": "i"}},
            {"notes": {"$regex": search, "$options": "i"}},
        ]
    docs = get_documents("activity", query)
    return [serialize_doc(d) for d in docs]

@app.get("/api/activities/{activity_id}")
async def get_activity(activity_id: str):
    doc = db["activity"].find_one({"_id": to_object_id(activity_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return serialize_doc(doc)

@app.put("/api/activities/{activity_id}")
async def update_activity(activity_id: str, payload: ActivityUpdate):
    update_data = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update_data:
        return {"updated": False}
    update_data["updated_at"] = datetime.utcnow()
    res = db["activity"].update_one({"_id": to_object_id(activity_id)}, {"$set": update_data})
    return {"updated": res.modified_count == 1}

@app.delete("/api/activities/{activity_id}")
async def delete_activity(activity_id: str):
    res = db["activity"].delete_one({"_id": to_object_id(activity_id)})
    return {"deleted": res.deleted_count == 1}

# File upload handling
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        filepath = os.path.join(UPLOAD_DIR, f"{int(datetime.utcnow().timestamp())}_{file.filename}")
        with open(filepath, "wb") as f:
            f.write(await file.read())
        url = f"/files/{os.path.basename(filepath)}"
        return {"filename": file.filename, "url": url, "content_type": file.content_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/{filename}")
async def serve_file(filename: str):
    filepath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)

# Dashboard aggregates
@app.get("/api/dashboard")
async def dashboard(month: Optional[int] = None, year: Optional[int] = None):
    y = year or datetime.utcnow().year
    m = month or datetime.utcnow().month
    start = datetime(y, m, 1)
    end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)

    match_stage = {"$match": {"date": {"$gte": start.date(), "$lt": end.date()}}}

    pipeline = [match_stage,
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1}
        }}
    ]
    cat_counts = list(db["activity"].aggregate(pipeline))

    finance_pipeline = [match_stage,
        {"$group": {
            "_id": None,
            "income": {"$sum": {"$ifNull": ["$income", 0]}},
            "expense": {"$sum": {"$ifNull": ["$expense", 0]}}
        }}
    ]
    finance = list(db["activity"].aggregate(finance_pipeline))
    total_income = finance[0]["income"] if finance else 0
    total_expense = finance[0]["expense"] if finance else 0

    total_activities = db["activity"].count_documents(match_stage["$match"])

    return {
        "total_activities": total_activities,
        "total_income": total_income,
        "total_expense": total_expense,
        "per_category": {item["_id"] or "unknown": item["count"] for item in cat_counts}
    }

# Monthly recap
class RecapRequest(BaseModel):
    month: Optional[int] = None
    year: Optional[int] = None

@app.post("/api/recap")
async def monthly_recap(payload: RecapRequest):
    y = payload.year or datetime.utcnow().year
    m = payload.month or datetime.utcnow().month
    start = datetime(y, m, 1)
    end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)

    match = {"date": {"$gte": start.date(), "$lt": end.date()}}

    cat_pipeline = [
        {"$match": match},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]
    categories = {doc["_id"] or "unknown": doc["count"] for doc in db["activity"].aggregate(cat_pipeline)}

    finance_pipeline = [
        {"$match": match},
        {"$group": {"_id": None, "income": {"$sum": {"$ifNull": ["$income", 0]}}, "expense": {"$sum": {"$ifNull": ["$expense", 0]}}}}
    ]
    finance = list(db["activity"].aggregate(finance_pipeline))
    total_income = finance[0]["income"] if finance else 0
    total_expense = finance[0]["expense"] if finance else 0

    summary = f"Bulan {m}/{y}: Total kegiatan {sum(categories.values())}. " \
              f"Kategori terbanyak: {max(categories, key=categories.get) if categories else 'N/A'}. " \
              f"Pemasukan {total_income:.2f}, Pengeluaran {total_expense:.2f}."

    return {
        "month": m,
        "year": y,
        "categories": categories,
        "income": total_income,
        "expense": total_expense,
        "summary": summary,
    }

# Export endpoints (CSV and text-as-pdf placeholder)
@app.get("/api/export/csv")
async def export_csv(month: Optional[int] = None, year: Optional[int] = None):
    import csv
    from io import StringIO
    activities = await list_activities(month=month, year=year)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tanggal", "Nama", "Kategori", "Durasi", "Hasil", "Catatan", "Pemasukan", "Pengeluaran", "Kategori Keuangan"])
    for a in activities:
        writer.writerow([
            a.get("date"), a.get("name"), a.get("category"), a.get("duration"), a.get("result"), a.get("notes"), a.get("income"), a.get("expense"), a.get("finance_category")
        ])
    output.seek(0)
    content = output.getvalue()
    filename = f"laporan_{year or datetime.utcnow().year}_{month or datetime.utcnow().month}.csv"
    from fastapi.responses import Response
    return Response(content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.get("/api/export/pdf")
async def export_pdf(month: Optional[int] = None, year: Optional[int] = None):
    recap = await monthly_recap(RecapRequest(month=month, year=year))
    activities = await list_activities(month=month, year=year)
    lines = [
        "Laporan Bulanan",
        f"Bulan: {recap['month']}/{recap['year']}",
        recap["summary"],
        "",
        "Rincian Kegiatan:",
    ]
    for a in activities:
        lines.append(f"- {a.get('date')} | {a.get('name')} | {a.get('category')} | {a.get('duration')} jam")
    content = "\n".join(lines)
    from fastapi.responses import Response
    filename = f"laporan_{year or datetime.utcnow().year}_{month or datetime.utcnow().month}.txt"
    return Response(content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={filename}"})

# Schema endpoint
@app.get("/schema")
def get_schema_info():
    from schemas import Activity  # ensure fresh schema
    return {"collections": [
        {"name": "activity", "model": Activity.model_json_schema()},
    ]}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
