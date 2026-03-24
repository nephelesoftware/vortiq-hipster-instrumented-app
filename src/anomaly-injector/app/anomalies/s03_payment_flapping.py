import asyncio
import logging
from typing import Optional

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)

FLAP_INTERVAL_SECONDS = 20


class PaymentFlapping(AnomalyBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._flap_task: Optional[asyncio.Task] = None

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s03_payment_flapping",
            name="Payment Service Flapping",
            description=(
                "Repeatedly kills the paymentservice pod every 20 seconds, causing "
                "Kubernetes to restart it.  Simulates an intermittently crashing service "
                "that triggers error-rate spikes on each kill cycle."
            ),
            affected_services=["paymentservice", "checkoutservice"],
            expected_impact=(
                "Intermittent payment failures, checkout error rate spikes every ~20s, "
                "pod restart counter increases"
            ),
            status=AnomalyStatus.IDLE,
        )

    async def _flap_loop(self) -> None:
        """Background loop that kills the paymentservice pod every FLAP_INTERVAL_SECONDS."""
        while True:
            try:
                pods = self.k8s.get_pods(self.NAMESPACE, "app=paymentservice")
                if pods:
                    pod_name = pods[0].metadata.name
                    self.k8s._core_v1.delete_namespaced_pod(
                        name=pod_name, namespace=self.NAMESPACE
                    )
                    logger.info("Flapped paymentservice pod %s", pod_name)
                else:
                    logger.warning("No paymentservice pods found during flap iteration")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Error during payment flap iteration: %s", exc)

            await asyncio.sleep(FLAP_INTERVAL_SECONDS)

    async def _start_impl(self, params: dict) -> None:
        self._flap_task = asyncio.create_task(self._flap_loop())
        logger.info("Started payment flapping background task (interval %ds)", FLAP_INTERVAL_SECONDS)

    async def _stop_impl(self) -> None:
        if self._flap_task and not self._flap_task.done():
            self._flap_task.cancel()
            try:
                await self._flap_task
            except asyncio.CancelledError:
                pass
            logger.info("Cancelled payment flapping background task")
        self._flap_task = None
