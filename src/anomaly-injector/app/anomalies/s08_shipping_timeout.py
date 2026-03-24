import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)


class ShippingTimeout(AnomalyBase):
    _original_replicas: int = 1

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s08_shipping_timeout",
            name="Shipping Service Timeout Storm",
            description=(
                "Scales the shippingservice deployment to 0 replicas so that checkout "
                "requests for shipping quotes hang until the gRPC/HTTP timeout fires.  "
                "Restores the original replica count on stop."
            ),
            affected_services=["shippingservice", "checkoutservice"],
            expected_impact=(
                "Checkout hangs waiting for shipping quotes, timeout errors, "
                "checkoutservice error rate spikes"
            ),
            status=AnomalyStatus.IDLE,
        )

    async def _start_impl(self, params: dict) -> None:
        self._original_replicas = self.k8s.get_deployment_replicas(
            self.NAMESPACE, "shippingservice"
        )
        logger.info("Saving shippingservice replica count: %d", self._original_replicas)
        self.k8s.scale_deployment(self.NAMESPACE, "shippingservice", 0)
        logger.info("Scaled shippingservice to 0")

    async def _stop_impl(self) -> None:
        restore = self._original_replicas if self._original_replicas > 0 else 1
        self.k8s.scale_deployment(self.NAMESPACE, "shippingservice", restore)
        logger.info("Restored shippingservice to %d replicas", restore)
        self._original_replicas = 1
