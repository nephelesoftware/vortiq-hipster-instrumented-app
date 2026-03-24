import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)


class TrafficBurst(AnomalyBase):
    _original_replicas: int = 1

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s09_traffic_burst",
            name="Traffic Burst / Flash Sale",
            description=(
                "Simulates a flash-sale traffic surge by scaling the loadgenerator to 5 "
                "replicas and setting USERS=50 per replica, producing approximately 5x "
                "normal request volume across all storefront services."
            ),
            affected_services=[
                "frontend",
                "productcatalogservice",
                "currencyservice",
                "cartservice",
                "checkoutservice",
                "adservice",
            ],
            expected_impact=(
                "5x traffic increase across all services, latency percentiles spike, "
                "potential connection pool exhaustion"
            ),
            status=AnomalyStatus.IDLE,
            parameters={"replicas": 5, "users_per_replica": 50},
        )

    async def _start_impl(self, params: dict) -> None:
        replicas = int(params.get("replicas", 5))
        users_per_replica = int(params.get("users_per_replica", 50))

        self._original_replicas = self.k8s.get_deployment_replicas(
            self.NAMESPACE, "loadgenerator"
        )
        logger.info("Saving loadgenerator replica count: %d", self._original_replicas)

        self.k8s.scale_deployment(self.NAMESPACE, "loadgenerator", replicas)
        logger.info("Scaled loadgenerator to %d replicas", replicas)

        self.k8s.patch_deployment_env(
            self.NAMESPACE, "loadgenerator", {"USERS": str(users_per_replica)}
        )
        logger.info("Set loadgenerator USERS=%d", users_per_replica)

    async def _stop_impl(self) -> None:
        restore = self._original_replicas if self._original_replicas > 0 else 1
        self.k8s.scale_deployment(self.NAMESPACE, "loadgenerator", restore)
        logger.info("Restored loadgenerator to %d replicas", restore)

        self.k8s.patch_deployment_env(
            self.NAMESPACE, "loadgenerator", {"USERS": "10"}
        )
        logger.info("Restored loadgenerator USERS=10")
        self._original_replicas = 1
