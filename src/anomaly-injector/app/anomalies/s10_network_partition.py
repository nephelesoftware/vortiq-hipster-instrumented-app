import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)

# Callers of each service — used to report affected_services dynamically
_SERVICE_CALLERS: dict = {
    "productcatalogservice": ["frontend", "recommendationservice", "checkoutservice"],
    "currencyservice": ["frontend", "checkoutservice"],
    "cartservice": ["frontend", "checkoutservice"],
    "shippingservice": ["checkoutservice"],
    "paymentservice": ["checkoutservice"],
    "emailservice": ["checkoutservice"],
    "recommendationservice": ["frontend"],
    "adservice": ["frontend"],
    "checkoutservice": ["frontend"],
}


class NetworkPartition(AnomalyBase):
    _original_replicas: int = 1
    _target_service: str = "productcatalogservice"

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s10_network_partition",
            name="Network Partition (Service Blackout)",
            description=(
                "Scales a target service to 0 replicas, simulating a hard network "
                "partition or complete service blackout.  All callers immediately receive "
                "connection-refused errors rather than slow responses."
            ),
            affected_services=_SERVICE_CALLERS.get(
                "productcatalogservice",
                ["frontend", "recommendationservice", "checkoutservice"],
            )
            + ["productcatalogservice"],
            expected_impact=(
                "Hard errors (not slow) for all callers of target service, "
                "immediate error rate spike, recovery visible on restore"
            ),
            status=AnomalyStatus.IDLE,
            parameters={"target_service": "productcatalogservice"},
        )

    async def _start_impl(self, params: dict) -> None:
        target = params.get("target_service", "productcatalogservice")
        self._target_service = target

        self._original_replicas = self.k8s.get_deployment_replicas(
            self.NAMESPACE, target
        )
        logger.info("Saving %s replica count: %d", target, self._original_replicas)

        # Update affected_services dynamically based on chosen target
        callers = _SERVICE_CALLERS.get(target, [])
        self._info.affected_services = callers + [target]

        self.k8s.scale_deployment(self.NAMESPACE, target, 0)
        logger.info("Network partition: scaled %s to 0", target)

    async def _stop_impl(self) -> None:
        restore = self._original_replicas if self._original_replicas > 0 else 1
        self.k8s.scale_deployment(self.NAMESPACE, self._target_service, restore)
        logger.info(
            "Restored %s to %d replicas (network partition lifted)",
            self._target_service,
            restore,
        )
        self._original_replicas = 1
