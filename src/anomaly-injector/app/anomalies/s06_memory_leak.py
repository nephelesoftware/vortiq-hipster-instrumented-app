import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)

JOB_NAME = "memory-stressor"


def _build_memory_job_manifest(memory_mb: int) -> dict:
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
                            "name": "memory-stressor",
                            "image": "polinux/stress",
                            "command": ["stress"],
                            "args": [
                                "--vm", "1",
                                "--vm-bytes", f"{memory_mb}M",
                                "--vm-keep",
                                "-t", "300s",
                            ],
                            "resources": {
                                "limits": {"memory": "512Mi"},
                                "requests": {"memory": "100Mi"},
                            },
                        }
                    ],
                },
            },
        },
    }


class MemoryLeak(AnomalyBase):
    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s06_memory_leak",
            name="Memory Leak → OOM CrashLoop",
            description=(
                "Runs a memory-stressor Job using polinux/stress that allocates 450 MB "
                "inside a 512 Mi limit container, triggering an OOMKill.  Simulates a "
                "memory-leaking process that eventually crashes and restarts."
            ),
            affected_services=["productcatalogservice"],
            expected_impact=(
                "Memory usage climbs, pod OOMKilled, brief outage on restart, "
                "Kubernetes restart counter increases"
            ),
            status=AnomalyStatus.IDLE,
            parameters={"target_service": "productcatalogservice", "memory_mb": 450},
        )

    async def _start_impl(self, params: dict) -> None:
        memory_mb = int(params.get("memory_mb", 450))

        if self.k8s.job_exists(self.NAMESPACE, JOB_NAME):
            logger.warning("Job %s already exists — skipping create", JOB_NAME)
            return

        manifest = _build_memory_job_manifest(memory_mb)
        self.k8s.create_job(self.NAMESPACE, manifest)
        logger.info("Created memory stressor job %s (%d MB)", JOB_NAME, memory_mb)

    async def _stop_impl(self) -> None:
        if self.k8s.job_exists(self.NAMESPACE, JOB_NAME):
            self.k8s.delete_job(self.NAMESPACE, JOB_NAME)
            logger.info("Deleted memory stressor job %s", JOB_NAME)
        else:
            logger.warning("Job %s not found — already deleted or never started", JOB_NAME)
