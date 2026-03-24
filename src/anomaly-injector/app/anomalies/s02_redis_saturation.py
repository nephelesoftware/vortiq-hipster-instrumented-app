import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)

JOB_NAME = "redis-flood"


def _build_flood_job_manifest() -> dict:
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": JOB_NAME,
            "namespace": "hipster",
        },
        "spec": {
            "ttlSecondsAfterFinished": 60,
            "template": {
                "metadata": {"labels": {"app": JOB_NAME}},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "redis-flood",
                            "image": "redis:alpine",
                            "command": ["/bin/sh", "-c"],
                            "args": [
                                (
                                    "for i in $(seq 1 500); do "
                                    "redis-cli -h redis-cart -p 6379 "
                                    "SET \"flood_key_$i\" "
                                    "\"$(python3 -c \"print('x'*10000)\")\" "
                                    "EX 300; "
                                    "done; "
                                    "echo 'Flood complete'"
                                )
                            ],
                        }
                    ],
                },
            },
        },
    }


class RedisSaturation(AnomalyBase):
    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s02_redis_saturation",
            name="Redis Cart Saturation",
            description=(
                "Floods redis-cart with 500 large keys (10 KB each, TTL 300s) via a "
                "Kubernetes Job, simulating memory and CPU saturation on the Redis instance."
            ),
            affected_services=[
                "redis-cart",
                "cartservice",
                "checkoutservice",
                "frontend",
            ],
            expected_impact=(
                "Cart operations slow/fail, checkout fails, Redis memory/CPU spikes"
            ),
            status=AnomalyStatus.IDLE,
        )

    async def _start_impl(self, params: dict) -> None:
        if self.k8s.job_exists(self.NAMESPACE, JOB_NAME):
            logger.warning("Job %s already exists — skipping create", JOB_NAME)
            return

        manifest = _build_flood_job_manifest()
        self.k8s.create_job(self.NAMESPACE, manifest)
        logger.info("Created Redis flood job %s", JOB_NAME)

    async def _stop_impl(self) -> None:
        if self.k8s.job_exists(self.NAMESPACE, JOB_NAME):
            self.k8s.delete_job(self.NAMESPACE, JOB_NAME)
            logger.info("Deleted Redis flood job %s", JOB_NAME)
        else:
            logger.warning("Redis flood job %s not found — already deleted", JOB_NAME)

        # Best-effort flush of flood keys from Redis
        pods = self.k8s.get_pods(self.NAMESPACE, "app=redis-cart")
        if pods:
            pod_name = pods[0].metadata.name
            try:
                self.k8s.exec_in_pod(
                    self.NAMESPACE,
                    pod_name,
                    "redis",
                    ["redis-cli", "EVAL",
                     "local keys=redis.call('KEYS','flood_key_*') "
                     "if #keys>0 then return redis.call('DEL',unpack(keys)) end return 0",
                     "0"],
                )
                logger.info("Flushed flood keys from redis-cart")
            except Exception as exc:
                logger.warning("Could not flush flood keys from redis-cart: %s", exc)
