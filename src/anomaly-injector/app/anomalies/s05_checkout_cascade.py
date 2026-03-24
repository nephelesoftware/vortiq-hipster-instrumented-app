import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)


class CheckoutCascade(AnomalyBase):
    _pid: int = 0

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s05_checkout_cascade",
            name="Checkout Cascade Slowdown",
            description=(
                "Injects 1200ms ± 300ms network latency into the checkoutservice "
                "container network namespace.  Because checkout calls six downstream "
                "services, the latency cascades across the entire purchase flow."
            ),
            affected_services=[
                "checkoutservice",
                "paymentservice",
                "shippingservice",
                "emailservice",
                "cartservice",
                "currencyservice",
            ],
            expected_impact=(
                "Full checkout flow degraded, all 6 downstream services show increased "
                "latency in traces"
            ),
            status=AnomalyStatus.IDLE,
            parameters={"delay_ms": 1200, "jitter_ms": 300},
        )

    async def _start_impl(self, params: dict) -> None:
        delay_ms = int(params.get("delay_ms", 1200))
        jitter_ms = int(params.get("jitter_ms", 300))

        pods = self.k8s.get_pods(self.NAMESPACE, "app=checkoutservice")
        if not pods:
            raise RuntimeError("No checkoutservice pods found")

        pod = pods[0]
        pod_name = pod.metadata.name
        container_id = self.k8s.get_container_id(
            self.NAMESPACE, pod_name, "server"
        )
        pid = self.network.get_container_pid(container_id)
        self._pid = pid

        self.network.add_latency(pid, delay_ms, jitter_ms)
        logger.info(
            "Injected %dms ± %dms latency into checkoutservice pod %s (pid %d)",
            delay_ms,
            jitter_ms,
            pod_name,
            pid,
        )

    async def _stop_impl(self) -> None:
        if self._pid:
            try:
                self.network.remove_latency(self._pid)
                logger.info("Removed latency from checkoutservice (pid %d)", self._pid)
            finally:
                self._pid = 0
        else:
            logger.warning("No PID stored for checkoutservice — already cleaned up")
