import logging
from typing import Any, Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException
from kubernetes.stream import stream

logger = logging.getLogger(__name__)


class K8sClient:
    def __init__(self):
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except ConfigException:
            config.load_kube_config()
            logger.info("Loaded local kubeconfig")

        self._core_v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()
        self._batch_v1 = client.BatchV1Api()

    def get_pods(self, namespace: str, label_selector: str) -> List[Any]:
        """Return list of pod objects matching the label selector."""
        try:
            resp = self._core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector
            )
            return resp.items
        except ApiException as e:
            raise RuntimeError(
                f"Failed to list pods in {namespace} with selector {label_selector!r}: {e}"
            ) from e

    def get_pod(self, namespace: str, name: str) -> Any:
        """Return a single pod object."""
        try:
            return self._core_v1.read_namespaced_pod(name=name, namespace=namespace)
        except ApiException as e:
            raise RuntimeError(
                f"Failed to get pod {name} in {namespace}: {e}"
            ) from e

    def scale_deployment(self, namespace: str, name: str, replicas: int) -> None:
        """Scale a deployment to the given number of replicas."""
        try:
            self._apps_v1.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body={"spec": {"replicas": replicas}},
            )
            logger.info("Scaled deployment %s/%s to %d replicas", namespace, name, replicas)
        except ApiException as e:
            raise RuntimeError(
                f"Failed to scale deployment {name} in {namespace} to {replicas}: {e}"
            ) from e

    def get_deployment_replicas(self, namespace: str, name: str) -> int:
        """Return the current desired replica count of a deployment."""
        try:
            deploy = self._apps_v1.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            replicas = deploy.spec.replicas
            return replicas if replicas is not None else 0
        except ApiException as e:
            raise RuntimeError(
                f"Failed to get deployment {name} in {namespace}: {e}"
            ) from e

    def create_job(self, namespace: str, job_manifest: dict) -> Any:
        """Create a batch Job from the given manifest dict."""
        try:
            job = self._batch_v1.create_namespaced_job(
                namespace=namespace, body=job_manifest
            )
            logger.info(
                "Created job %s in %s", job_manifest.get("metadata", {}).get("name"), namespace
            )
            return job
        except ApiException as e:
            raise RuntimeError(
                f"Failed to create job in {namespace}: {e}"
            ) from e

    def delete_job(self, namespace: str, name: str) -> None:
        """Delete a batch Job (and its pods) by name."""
        try:
            self._batch_v1.delete_namespaced_job(
                name=name,
                namespace=namespace,
                body=client.V1DeleteOptions(propagation_policy="Foreground"),
            )
            logger.info("Deleted job %s in %s", name, namespace)
        except ApiException as e:
            if e.status == 404:
                logger.warning("Job %s not found in %s, skipping delete", name, namespace)
                return
            raise RuntimeError(
                f"Failed to delete job {name} in {namespace}: {e}"
            ) from e

    def job_exists(self, namespace: str, name: str) -> bool:
        """Return True if a Job with the given name exists."""
        try:
            self._batch_v1.read_namespaced_job(name=name, namespace=namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise RuntimeError(
                f"Failed to check job {name} in {namespace}: {e}"
            ) from e

    def exec_in_pod(
        self,
        namespace: str,
        pod_name: str,
        container: str,
        command: List[str],
    ) -> str:
        """Execute a command in a running pod container and return stdout."""
        try:
            resp = stream(
                self._core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                container=container,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
            return resp
        except ApiException as e:
            raise RuntimeError(
                f"Failed to exec in pod {pod_name}/{container} in {namespace}: {e}"
            ) from e

    def patch_deployment_env(
        self, namespace: str, name: str, env_vars: Dict[str, str]
    ) -> None:
        """Patch the first container's env vars on a deployment."""
        try:
            deploy = self._apps_v1.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            container = deploy.spec.template.spec.containers[0]
            existing_env = {e.name: e for e in (container.env or [])}

            for key, value in env_vars.items():
                existing_env[key] = client.V1EnvVar(name=key, value=str(value))

            container.env = list(existing_env.values())

            self._apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deploy,
            )
            logger.info(
                "Patched deployment %s/%s env vars: %s", namespace, name, env_vars
            )
        except ApiException as e:
            raise RuntimeError(
                f"Failed to patch deployment env {name} in {namespace}: {e}"
            ) from e

    def get_container_id(
        self, namespace: str, pod_name: str, container_name: str
    ) -> str:
        """Return the container ID without the runtime prefix (e.g. 'containerd://')."""
        pod = self.get_pod(namespace, pod_name)
        for status in pod.status.container_statuses or []:
            if status.name == container_name:
                raw_id = status.container_id or ""
                # Strip runtime prefix like "containerd://" or "docker://"
                if "://" in raw_id:
                    return raw_id.split("://", 1)[1]
                return raw_id
        raise RuntimeError(
            f"Container {container_name!r} not found in pod {pod_name} in {namespace}"
        )
