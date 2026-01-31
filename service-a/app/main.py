import os
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI(title="service-a")

SERVICE_B_BASE_URL = os.getenv("SERVICE_B_BASE_URL", "http://localhost:8001")


class CreateOrderRequest(BaseModel):
    sku: str
    qty: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-a", "serviceB": SERVICE_B_BASE_URL}


@app.post("/orders", status_code=201)
async def create_order(req: CreateOrderRequest):
    if req.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    order_id = str(uuid.uuid4())

    timeout = httpx.Timeout(1.0)  # 1 second total timeout for the call

    # Call service-b to "reserve" inventory
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{SERVICE_B_BASE_URL}/reserve",
                json={"orderId": order_id, "sku": req.sku, "qty": req.qty},
            )
            resp.raise_for_status()
            reservation = resp.json()

    except httpx.TimeoutException:
        # This is the key learning: downstream is too slow for our SLA
        raise HTTPException(status_code=504, detail="Timeout calling service-b /reserve")

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"service-b error: {e.response.text}")

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"network error calling service-b: {str(e)}")


    return {
        "orderId": order_id,
        "status": "created",
        "reservation": reservation,
    }
