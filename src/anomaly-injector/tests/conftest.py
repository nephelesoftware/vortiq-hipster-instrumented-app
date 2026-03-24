import pytest
from unittest.mock import MagicMock

from app.k8s_client import K8sClient
from app.network_chaos import NetworkChaos


@pytest.fixture
def mock_k8s():
    k8s = MagicMock(spec=K8sClient)
    k8s.scale_deployment = MagicMock()
    k8s.get_pods = MagicMock()
    k8s.get_deployment_replicas = MagicMock(return_value=1)
    k8s.create_job = MagicMock()
    k8s.delete_job = MagicMock()
    k8s.job_exists = MagicMock(return_value=False)
    k8s.exec_in_pod = MagicMock(return_value="OK")
    k8s.get_container_id = MagicMock(return_value="abc123def456")
    k8s.patch_deployment_env = MagicMock()
    return k8s


@pytest.fixture
def mock_network():
    net = MagicMock(spec=NetworkChaos)
    net.get_container_pid = MagicMock(return_value=12345)
    net.add_latency = MagicMock()
    net.remove_latency = MagicMock()
    net.add_packet_loss = MagicMock()
    return net


def make_mock_pod(name: str = "test-pod-abc123", container_name: str = "server"):
    """Return a minimal mock pod object."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.status.container_statuses = [MagicMock()]
    pod.status.container_statuses[0].name = container_name
    pod.status.container_statuses[0].container_id = f"containerd://abc123def456"
    return pod
