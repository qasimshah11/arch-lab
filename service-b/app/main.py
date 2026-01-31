import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

reserve_call_count_by_order = {}



app = FastAPI(title="service-b")

PORT = int(os.getenv("PORT", "8001"))
DELAY_MS = int(os.getenv("DELAY_MS", "0"))  # we'll use this later for timeout drills


class ReserveRequest(BaseModel):
    orderId: str
    sku: str
    qty: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-b"}


@app.post("/reserve")
async def reserve(req: ReserveRequest):
    # Optional artificial delay (for future drills)
    if DELAY_MS > 0:
        await asyncio.sleep(DELAY_MS / 1000)

    if req.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    count = reserve_call_count_by_order.get(req.orderId, 0) + 1
    reserve_call_count_by_order[req.orderId] = count

    print(f"[service-b] reserve called for orderId={req.orderId} count={count}")

    return {
        "reservationId": str(uuid.uuid4()),
        "status": "reserved",
        "sku": req.sku,
        "qty": req.qty,
        "callCountForOrderId": count
    }
