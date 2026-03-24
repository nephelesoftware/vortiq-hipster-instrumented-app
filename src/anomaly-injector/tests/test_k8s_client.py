from unittest.mock import MagicMock, patch, call

import pytest
from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_exception(status: int = 500) -> ApiException:
    exc = ApiException(status=status)
    exc.status = status
    return exc


def _make_pod(name: str, container_name: str = "server", container_id: str = "containerd://abc123"):
    pod = MagicMock()
    pod.metadata.name = name
    cs = MagicMock()
    cs.name = container_name
    cs.container_id = container_id
    pod.status.container_statuses = [cs]
    return pod


# ---------------------------------------------------------------------------
# We patch the kubernetes library at import time so K8sClient.__init__ doesn't
# attempt a real cluster connection.
# ---------------------------------------------------------------------------

@pytest.fixture
def k8s_client():
    with patch("app.k8s_client.config") as mock_cfg, \
         patch("app.k8s_client.client") as mock_client:

        mock_cfg.load_incluster_config.side_effect = ConfigException("not in cluster")
        mock_cfg.load_kube_config.return_value = None

        # Stub the three API class constructors
        core = MagicMock()
        apps = MagicMock()
        batch = MagicMock()
        mock_client.CoreV1Api.return_value = core
        mock_client.AppsV1Api.return_value = apps
        mock_client.BatchV1Api.return_value = batch
        mock_client.V1DeleteOptions.return_value = MagicMock()
        mock_client.V1EnvVar = MagicMock(side_effect=lambda name, value: MagicMock(name=name, value=value))

        from app.k8s_client import K8sClient
        client_obj = K8sClient()
        client_obj._core_v1 = core
        client_obj._apps_v1 = apps
        client_obj._batch_v1 = batch

        yield client_obj, core, apps, batch


# ---------------------------------------------------------------------------
# get_pods
# ---------------------------------------------------------------------------

class TestGetPods:
    def test_success(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        pod = _make_pod("pod-1")
        core.list_namespaced_pod.return_value = MagicMock(items=[pod])

        result = client_obj.get_pods("hipster", "app=frontend")

        assert result == [pod]
        core.list_namespaced_pod.assert_called_once_with(
            namespace="hipster", label_selector="app=frontend"
        )

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        core.list_namespaced_pod.side_effect = _make_api_exception()

        with pytest.raises(RuntimeError, match="Failed to list pods"):
            client_obj.get_pods("hipster", "app=frontend")


# ---------------------------------------------------------------------------
# get_pod
# ---------------------------------------------------------------------------

class TestGetPod:
    def test_success(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        pod = _make_pod("my-pod")
        core.read_namespaced_pod.return_value = pod

        result = client_obj.get_pod("hipster", "my-pod")
        assert result == pod

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        core.read_namespaced_pod.side_effect = _make_api_exception()

        with pytest.raises(RuntimeError, match="Failed to get pod"):
            client_obj.get_pod("hipster", "my-pod")


# ---------------------------------------------------------------------------
# scale_deployment
# ---------------------------------------------------------------------------

class TestScaleDeployment:
    def test_success(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        apps.patch_namespaced_deployment_scale.return_value = MagicMock()

        client_obj.scale_deployment("hipster", "frontend", 3)
        apps.patch_namespaced_deployment_scale.assert_called_once_with(
            name="frontend", namespace="hipster", body={"spec": {"replicas": 3}}
        )

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        apps.patch_namespaced_deployment_scale.side_effect = _make_api_exception()

        with pytest.raises(RuntimeError, match="Failed to scale deployment"):
            client_obj.scale_deployment("hipster", "frontend", 0)


# ---------------------------------------------------------------------------
# get_deployment_replicas
# ---------------------------------------------------------------------------

class TestGetDeploymentReplicas:
    def test_success(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        deploy = MagicMock()
        deploy.spec.replicas = 2
        apps.read_namespaced_deployment.return_value = deploy

        assert client_obj.get_deployment_replicas("hipster", "frontend") == 2

    def test_none_replicas_returns_zero(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        deploy = MagicMock()
        deploy.spec.replicas = None
        apps.read_namespaced_deployment.return_value = deploy

        assert client_obj.get_deployment_replicas("hipster", "frontend") == 0

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        apps.read_namespaced_deployment.side_effect = _make_api_exception()

        with pytest.raises(RuntimeError, match="Failed to get deployment"):
            client_obj.get_deployment_replicas("hipster", "frontend")


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_success(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        job = MagicMock()
        batch.create_namespaced_job.return_value = job

        manifest = {"metadata": {"name": "test-job"}, "spec": {}}
        result = client_obj.create_job("hipster", manifest)
        assert result == job

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        batch.create_namespaced_job.side_effect = _make_api_exception()

        with pytest.raises(RuntimeError, match="Failed to create job"):
            client_obj.create_job("hipster", {})


# ---------------------------------------------------------------------------
# delete_job
# ---------------------------------------------------------------------------

class TestDeleteJob:
    def test_success(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        batch.delete_namespaced_job.return_value = MagicMock()

        client_obj.delete_job("hipster", "my-job")
        batch.delete_namespaced_job.assert_called_once()

    def test_404_does_not_raise(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        exc = _make_api_exception(404)
        batch.delete_namespaced_job.side_effect = exc

        # Should not raise
        client_obj.delete_job("hipster", "missing-job")

    def test_non_404_raises_runtime_error(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        batch.delete_namespaced_job.side_effect = _make_api_exception(500)

        with pytest.raises(RuntimeError, match="Failed to delete job"):
            client_obj.delete_job("hipster", "my-job")


# ---------------------------------------------------------------------------
# job_exists
# ---------------------------------------------------------------------------

class TestJobExists:
    def test_exists_returns_true(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        batch.read_namespaced_job.return_value = MagicMock()

        assert client_obj.job_exists("hipster", "my-job") is True

    def test_not_found_returns_false(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        batch.read_namespaced_job.side_effect = _make_api_exception(404)

        assert client_obj.job_exists("hipster", "my-job") is False

    def test_other_exception_raises_runtime_error(self, k8s_client):
        client_obj, _, _, batch = k8s_client
        batch.read_namespaced_job.side_effect = _make_api_exception(503)

        with pytest.raises(RuntimeError, match="Failed to check job"):
            client_obj.job_exists("hipster", "my-job")


# ---------------------------------------------------------------------------
# exec_in_pod
# ---------------------------------------------------------------------------

class TestExecInPod:
    def test_success(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        with patch("app.k8s_client.stream") as mock_stream:
            mock_stream.return_value = "OK"
            result = client_obj.exec_in_pod("hipster", "pod-1", "server", ["ls"])
            assert result == "OK"

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        with patch("app.k8s_client.stream") as mock_stream:
            mock_stream.side_effect = _make_api_exception()
            with pytest.raises(RuntimeError, match="Failed to exec in pod"):
                client_obj.exec_in_pod("hipster", "pod-1", "server", ["ls"])


# ---------------------------------------------------------------------------
# patch_deployment_env
# ---------------------------------------------------------------------------

class TestPatchDeploymentEnv:
    def test_success_adds_env_var(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        deploy = MagicMock()
        container = MagicMock()
        env_var = MagicMock()
        env_var.name = "EXISTING"
        container.env = [env_var]
        deploy.spec.template.spec.containers = [container]
        apps.read_namespaced_deployment.return_value = deploy

        client_obj.patch_deployment_env("hipster", "loadgenerator", {"USERS": "50"})
        apps.patch_namespaced_deployment.assert_called_once()

    def test_api_exception_raises_runtime_error(self, k8s_client):
        client_obj, _, apps, _ = k8s_client
        apps.read_namespaced_deployment.side_effect = _make_api_exception()

        with pytest.raises(RuntimeError, match="Failed to patch deployment env"):
            client_obj.patch_deployment_env("hipster", "frontend", {"KEY": "val"})


# ---------------------------------------------------------------------------
# get_container_id
# ---------------------------------------------------------------------------

class TestGetContainerId:
    def test_success_strips_prefix(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        pod = _make_pod("pod-1", "server", "containerd://abc123def456")
        core.read_namespaced_pod.return_value = pod

        result = client_obj.get_container_id("hipster", "pod-1", "server")
        assert result == "abc123def456"

    def test_success_docker_prefix(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        pod = _make_pod("pod-1", "server", "docker://deadbeef1234")
        core.read_namespaced_pod.return_value = pod

        result = client_obj.get_container_id("hipster", "pod-1", "server")
        assert result == "deadbeef1234"

    def test_container_not_found_raises_runtime_error(self, k8s_client):
        client_obj, core, _, _ = k8s_client
        pod = _make_pod("pod-1", "other-container", "containerd://abc123")
        core.read_namespaced_pod.return_value = pod

        with pytest.raises(RuntimeError, match="not found in pod"):
            client_obj.get_container_id("hipster", "pod-1", "server")
