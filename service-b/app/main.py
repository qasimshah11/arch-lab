import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

reserve_call_count_by_order = {}



app = FastAPI(title="service-b")

PORT = int(os.getenv("PORT", "8001"))
DELAY_MS = int(os.getenv("DELAY_MS", "0"))  # we'll use this later for timeout drills

FAIL_AFTER_STORE_ONCE = os.getenv("FAIL_AFTER_STORE_ONCE", "0") == "1"

reservation_by_order_id = {}      # orderId -> reservation payload
failed_once_by_order_id = set()   # track which orderIds we've already failed once for
lock = asyncio.Lock()


class ReserveRequest(BaseModel):
    orderId: str
    sku: str
    qty: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-b"}


"""
Flow of this endpoint:
1. Validates the request quantity (qty > 0).
2. Waits for DELAY_MS if set (simulates slow processing).
3. Uses a lock to prevent race conditions (thread safety).
4. Checks if the orderId was already processed:
- If yes: returns the same reservation (idempotent, no duplicate).
- If no: creates a new reservation, stores it, and returns it.
5. If FAIL_AFTER_STORE_ONCE is set, simulates a crash after storing the reservation (so the caller retries).
6. On retry, returns the same reservation for the same orderId.

This simulates a real-world scenario:
- Service A asks to reserve stock for an order.
- Service B stores the reservation, but fails before responding (side effect happened, but caller thinks it failed).
- Service A retries the request.
- Service B sees the same orderId and returns the same reservation (no duplicate side effect).
"""
@app.post("/reserve")
async def reserve(req: ReserveRequest):
    if req.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    # Optional artificial delay (still available, but we set DELAY_MS=0 for this step)
    if DELAY_MS > 0:
        await asyncio.sleep(DELAY_MS / 1000)

    async with lock:
        # ✅ Idempotency: if we've already processed this orderId, return same result
        if req.orderId in reservation_by_order_id:
            existing = reservation_by_order_id[req.orderId]
            existing["replayed"] = True
            print(f"[service-b] REPLAY orderId={req.orderId} reservationId={existing['reservationId']}", flush=True)
            return existing

        # First time seeing this orderId: create reservation once
        reservation = {
            "reservationId": str(uuid.uuid4()),
            "status": "reserved",
            "sku": req.sku,
            "qty": req.qty,
            "callCountForOrderId": 1,
            "replayed": False
        }

        reservation_by_order_id[req.orderId] = reservation
        print(f"[service-b] CREATE orderId={req.orderId} reservationId={reservation['reservationId']}")

        # ✅ Failure injection: simulate "side effect happened but response failed"
        if FAIL_AFTER_STORE_ONCE and req.orderId not in failed_once_by_order_id:
            failed_once_by_order_id.add(req.orderId)
            print(f"[service-b] SIMULATED FAILURE after storing reservation for orderId={req.orderId}", flush=True)
            raise HTTPException(status_code=500, detail="Simulated failure AFTER reservation stored")

        return reservation

