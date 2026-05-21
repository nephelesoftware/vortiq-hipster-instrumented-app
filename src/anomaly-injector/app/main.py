import logging
import os
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.anomalies import get_all_anomalies
from app.k8s_client import K8sClient
from app.models import AnomalyInfo, AnomalyStartRequest
from app.network_chaos import NetworkChaos

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Anomaly Injector", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise Kubernetes and network clients, then build the anomaly registry.
k8s = K8sClient()
network = NetworkChaos()
anomalies = get_all_anomalies(k8s, network)

# Serve the static dashboard at /static/*
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(
        os.path.join(_static_dir, "index.html"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/anomalies", response_model=List[AnomalyInfo])
async def list_anomalies() -> List[AnomalyInfo]:
    """Return the current state of all 10 anomaly scenarios."""
    return [a.info for a in anomalies.values()]


@app.get("/api/anomalies/{anomaly_id}", response_model=AnomalyInfo)
async def get_anomaly(anomaly_id: str) -> AnomalyInfo:
    """Return the state of a single anomaly scenario."""
    if anomaly_id not in anomalies:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id!r} not found")
    return anomalies[anomaly_id].info


@app.post("/api/anomalies/{anomaly_id}/start", response_model=AnomalyInfo)
async def start_anomaly(
    anomaly_id: str,
    request: AnomalyStartRequest = AnomalyStartRequest(),
) -> AnomalyInfo:
    """Start an anomaly scenario with optional parameter overrides."""
    if anomaly_id not in anomalies:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id!r} not found")
    try:
        return await anomalies[anomaly_id].start(request)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error starting anomaly %s", anomaly_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anomalies/{anomaly_id}/stop", response_model=AnomalyInfo)
async def stop_anomaly(anomaly_id: str) -> AnomalyInfo:
    """Stop a running anomaly scenario and restore normal service state."""
    if anomaly_id not in anomalies:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id!r} not found")
    try:
        return await anomalies[anomaly_id].stop()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error stopping anomaly %s", anomaly_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}
