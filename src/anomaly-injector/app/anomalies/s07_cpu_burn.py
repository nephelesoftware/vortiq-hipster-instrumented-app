import logging

from app.models import AnomalyInfo, AnomalyStatus
from .base import AnomalyBase

logger = logging.getLogger(__name__)

JOB_NAME = "cpu-stressor"


def _build_cpu_job_manifest(cpu_workers: int) -> dict:
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
                            "name": "cpu-stressor",
                            "image": "polinux/stress",
                            "command": ["stress"],
                            "args": [
                                "--cpu", str(cpu_workers),
                                "-t", "300s",
                            ],
                            "resources": {
                                "requests": {"cpu": "100m"},
                            },
                        }
                    ],
                },
            },
        },
    }


class CpuBurn(AnomalyBase):
    def _build_info(self) -> AnomalyInfo:
        return AnomalyInfo(
            id="s07_cpu_burn",
            name="CPU Burn",
            description=(
                "Runs a cpu-stressor Job using polinux/stress with 4 worker threads "
                "that spin at 100% CPU for 5 minutes.  No CPU limit is set so the "
                "stressor can saturate available node capacity."
            ),
            affected_services=["frontend", "checkoutservice"],
            expected_impact=(
                "Node CPU saturated, all services show increased latency, "
                "response times degrade uniformly"
            ),
            status=AnomalyStatus.IDLE,
            parameters={"cpu_workers": 4},
        )

    async def _start_impl(self, params: dict) -> None:
        cpu_workers = int(params.get("cpu_workers", 4))

        if self.k8s.job_exists(self.NAMESPACE, JOB_NAME):
            logger.warning("Job %s already exists — skipping create", JOB_NAME)
            return

        manifest = _build_cpu_job_manifest(cpu_workers)
        self.k8s.create_job(self.NAMESPACE, manifest)
        logger.info("Created CPU stressor job %s (%d workers)", JOB_NAME, cpu_workers)

    async def _stop_impl(self) -> None:
        if self.k8s.job_exists(self.NAMESPACE, JOB_NAME):
            self.k8s.delete_job(self.NAMESPACE, JOB_NAME)
            logger.info("Deleted CPU stressor job %s", JOB_NAME)
        else:
            logger.warning("Job %s not found — already deleted or never started", JOB_NAME)
