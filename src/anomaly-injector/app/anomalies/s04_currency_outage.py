import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)


class CurrencyOutage(AnomalyBase):
    _original_replicas: int = 1

    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s04_currency_outage",
            name="Currency Service Outage",
            description=(
                "Scales the currencyservice deployment to 0 replicas, causing all "
                "currency-conversion calls to fail immediately.  Restores the original "
                "replica count on stop."
            ),
            affected_services=["currencyservice", "frontend", "checkoutservice"],
            expected_impact=(
                "All product prices fail to render, checkout cannot calculate totals, "
                "high error rate across all pages"
            ),
            status=AnomalyStatus.IDLE,
        )

    async def _start_impl(self, params: dict) -> None:
        self._original_replicas = self.k8s.get_deployment_replicas(
            self.NAMESPACE, "currencyservice"
        )
        logger.info(
            "Saving currencyservice replica count: %d", self._original_replicas
        )
        self.k8s.scale_deployment(self.NAMESPACE, "currencyservice", 0)
        logger.info("Scaled currencyservice to 0")

    async def _stop_impl(self) -> None:
        restore = self._original_replicas if self._original_replicas > 0 else 1
        self.k8s.scale_deployment(self.NAMESPACE, "currencyservice", restore)
        logger.info("Restored currencyservice to %d replicas", restore)
        self._original_replicas = 1
