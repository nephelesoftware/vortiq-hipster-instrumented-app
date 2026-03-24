from enum import Enum
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AnomalyStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


class AnomalyInfo(BaseModel):
    id: str
    name: str
    description: str
    affected_services: List[str]
    expected_impact: str
    status: AnomalyStatus = AnomalyStatus.IDLE
    started_at: Optional[datetime] = None
    error_message: Optional[str] = None
    parameters: dict = {}


class AnomalyStartRequest(BaseModel):
    parameters: dict = {}


class AnomalyStopRequest(BaseModel):
    pass
