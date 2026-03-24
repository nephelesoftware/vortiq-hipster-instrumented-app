import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)


class ProductCatalogLatency(AnomalyBase):
    _pid: int = 0

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s01_productcatalog_latency",
            name="Product Catalog Latency Spike",
            description=(
                "Injects 800ms ± 200ms network latency into the productcatalogservice "
                "container network namespace using tc netem, simulating a slow upstream "
                "data store or overloaded catalog backend."
            ),
            affected_services=[
                "productcatalogservice",
                "frontend",
                "recommendationservice",
                "checkoutservice",
            ],
            expected_impact=(
                "Product pages slow, recommendations delayed, checkout degraded across 3+ services"
            ),
            status=AnomalyStatus.IDLE,
            parameters={"delay_ms": 800, "jitter_ms": 200},
        )

    async def _start_impl(self, params: dict) -> None:
        delay_ms = int(params.get("delay_ms", 800))
        jitter_ms = int(params.get("jitter_ms", 200))

        pods = self.k8s.get_pods(
            self.NAMESPACE, "app=productcatalogservice"
        )
        if not pods:
            raise RuntimeError("No productcatalogservice pods found")

        pod = pods[0]
        pod_name = pod.metadata.name
        container_id = self.k8s.get_container_id(
            self.NAMESPACE, pod_name, "server"
        )
        pid = self.network.get_container_pid(container_id)
        self._pid = pid

        self.network.add_latency(pid, delay_ms, jitter_ms)
        logger.info(
            "Injected %dms ± %dms latency into productcatalogservice pod %s (pid %d)",
            delay_ms,
            jitter_ms,
            pod_name,
            pid,
        )

    async def _stop_impl(self) -> None:
        if self._pid:
            try:
                self.network.remove_latency(self._pid)
                logger.info(
                    "Removed latency from productcatalogservice (pid %d)", self._pid
                )
            finally:
                self._pid = 0
        else:
            logger.warning("No PID stored for productcatalogservice latency — already cleaned up")
