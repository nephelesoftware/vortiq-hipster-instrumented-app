import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.k8s_client import K8sClient
from app.models import AnomalyInfo, AnomalyStartRequest, AnomalyStatus
from app.network_chaos import NetworkChaos

logger = logging.getLogger(__name__)


class AnomalyBase(ABC):
    NAMESPACE = "hipster"

    def __init__(self, k8s: K8sClient, network: NetworkChaos):
        self.k8s = k8s
        self.network = network
        self._task: Optional[asyncio.Task] = None
        self._info = self._build_info()

    @abstractmethod
    def _build_info(self) -> AnomalyInfo:
        """Return a fully populated AnomalyInfo for this scenario."""
        ...

    @abstractmethod
    async def _start_impl(self, params: dict) -> None:
        """Implement the actual anomaly injection logic."""
        ...

    @abstractmethod
    async def _stop_impl(self) -> None:
        """Implement the cleanup / restoration logic."""
        ...

    async def start(self, request: AnomalyStartRequest) -> AnomalyInfo:
        """Start the anomaly.  Raises RuntimeError if already running."""
        if self._info.status == AnomalyStatus.RUNNING:
            raise RuntimeError(f"Anomaly {self._info.id} is already running")
        try:
            self._info.status = AnomalyStatus.RUNNING
            self._info.started_at = datetime.utcnow()
            self._info.error_message = None
            self._info.parameters = request.parameters
            await self._start_impl(request.parameters)
        except Exception as e:
            self._info.status = AnomalyStatus.ERROR
            self._info.error_message = str(e)
            raise
        return self._info

    async def stop(self) -> AnomalyInfo:
        """Stop the anomaly.  Raises RuntimeError if not running."""
        if self._info.status != AnomalyStatus.RUNNING:
            raise RuntimeError(f"Anomaly {self._info.id} is not running")
        try:
            self._info.status = AnomalyStatus.STOPPING
            await self._stop_impl()
            self._info.status = AnomalyStatus.IDLE
            self._info.started_at = None
        except Exception as e:
            self._info.status = AnomalyStatus.ERROR
            self._info.error_message = str(e)
            raise
        return self._info

    @property
    def info(self) -> AnomalyInfo:
        return self._info
