import os
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import asyncio

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

    timeout = httpx.Timeout(1.0)  # 1 second total timeout per attempt

    max_attempts = 3
    base_backoff_seconds = 0.2
    last_error = None


    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{SERVICE_B_BASE_URL}/reserve",
                    json={"orderId": order_id, "sku": req.sku, "qty": req.qty},
                )
                print(f"[service-a] reserve attempt {attempt} for orderId={order_id}", flush=True)
                resp.raise_for_status()
                reservation = resp.json()
                break  # success, exit retry loop

        except httpx.TimeoutException as e:
            last_error = e
            if attempt == max_attempts:
                raise HTTPException(status_code=504, detail="Timeout calling service-b /reserve (after retries)")
            await asyncio.sleep(base_backoff_seconds * (2 ** (attempt - 1)))

        except httpx.RequestError as e:
            # DNS issues, connection refused, etc. (retryable)
            last_error = e
            if attempt == max_attempts:
                raise HTTPException(status_code=502, detail=f"Network error calling service-b (after retries): {str(e)}")
            await asyncio.sleep(base_backoff_seconds * (2 ** (attempt - 1)))

        except httpx.HTTPStatusError as e:
            # If service-b returns 5xx, you *might* retry. If it returns 4xx, don't.
            status = e.response.status_code
            body = e.response.text

            if 500 <= status < 600 and attempt < max_attempts:
                last_error = e
                await asyncio.sleep(base_backoff_seconds * (2 ** (attempt - 1)))
                continue

            # Non-retryable (or final attempt)
            raise HTTPException(status_code=502, detail=f"service-b error ({status}): {body}")

    # If we somehow exit loop without reservation, fail safely
    if not reservation:
        raise HTTPException(status_code=502, detail=f"Failed calling service-b: {str(last_error)}")


    return {
        "orderId": order_id,
        "status": "created",
        "reservation": reservation,
    }
