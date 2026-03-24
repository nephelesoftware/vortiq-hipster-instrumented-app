from typing import Dict

from app.k8s_client import K8sClient
from app.network_chaos import NetworkChaos
from .base import AnomalyBase
from .s01_productcatalog_latency import ProductCatalogLatency
from .s02_redis_saturation import RedisSaturation
from .s03_payment_flapping import PaymentFlapping
from .s04_currency_outage import CurrencyOutage
from .s05_checkout_cascade import CheckoutCascade
from .s06_memory_leak import MemoryLeak
from .s07_cpu_burn import CpuBurn
from .s08_shipping_timeout import ShippingTimeout
from .s09_traffic_burst import TrafficBurst
from .s10_network_partition import NetworkPartition


def get_all_anomalies(k8s: K8sClient, network: NetworkChaos) -> Dict[str, AnomalyBase]:
    scenarios = [
        ProductCatalogLatency(k8s, network),
        RedisSaturation(k8s, network),
        PaymentFlapping(k8s, network),
        CurrencyOutage(k8s, network),
        CheckoutCascade(k8s, network),
        MemoryLeak(k8s, network),
        CpuBurn(k8s, network),
        ShippingTimeout(k8s, network),
        TrafficBurst(k8s, network),
        NetworkPartition(k8s, network),
    ]
    return {s.info.id: s for s in scenarios}
