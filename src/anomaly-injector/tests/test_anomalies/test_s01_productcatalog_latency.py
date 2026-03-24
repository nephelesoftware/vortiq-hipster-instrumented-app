import pytest
from unittest.mock import MagicMock

from app.anomalies.s01_productcatalog_latency import ProductCatalogLatency
from app.models import AnomalyStartRequest, AnomalyStatus


def _make_pod(name="productcatalogservice-abc"):
    pod = MagicMock()
    pod.metadata.name = name
    return pod


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return ProductCatalogLatency(mock_k8s, mock_network)


# ---------------------------------------------------------------------------

class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s01_productcatalog_latency"

    def test_name(self, scenario):
        assert "Latency" in scenario.info.name

    def test_affected_services_contains_productcatalog(self, scenario):
        assert "productcatalogservice" in scenario.info.affected_services

    def test_affected_services_multi_hop(self, scenario):
        svcs = scenario.info.affected_services
        assert "frontend" in svcs
        assert "recommendationservice" in svcs
        assert "checkoutservice" in svcs

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE

    def test_default_parameters(self, scenario):
        assert scenario.info.parameters.get("delay_ms") == 800
        assert scenario.info.parameters.get("jitter_ms") == 200


# ---------------------------------------------------------------------------

class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_calls_get_pods(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123def456"
        mock_network.get_container_pid.return_value = 42

        await scenario.start(AnomalyStartRequest())

        mock_k8s.get_pods.assert_called_once_with("hipster", "app=productcatalogservice")

    @pytest.mark.asyncio
    async def test_calls_get_container_id(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod("prod-pod-1")]
        mock_k8s.get_container_id.return_value = "abc123def456"
        mock_network.get_container_pid.return_value = 42

        await scenario.start(AnomalyStartRequest())

        mock_k8s.get_container_id.assert_called_once_with("hipster", "prod-pod-1", "server")

    @pytest.mark.asyncio
    async def test_calls_get_container_pid(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123def456"
        mock_network.get_container_pid.return_value = 99

        await scenario.start(AnomalyStartRequest())

        mock_network.get_container_pid.assert_called_once_with("abc123def456")

    @pytest.mark.asyncio
    async def test_calls_add_latency_with_defaults(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123def456"
        mock_network.get_container_pid.return_value = 55

        await scenario.start(AnomalyStartRequest())

        mock_network.add_latency.assert_called_once_with(55, 800, 200)

    @pytest.mark.asyncio
    async def test_calls_add_latency_with_custom_params(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 77

        await scenario.start(AnomalyStartRequest(parameters={"delay_ms": 400, "jitter_ms": 50}))

        mock_network.add_latency.assert_called_once_with(77, 400, 50)

    @pytest.mark.asyncio
    async def test_status_becomes_running(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123def456"
        mock_network.get_container_pid.return_value = 42

        info = await scenario.start(AnomalyStartRequest())
        assert info.status == AnomalyStatus.RUNNING


# ---------------------------------------------------------------------------

class TestStartAlreadyRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 42

        await scenario.start(AnomalyStartRequest())

        with pytest.raises(RuntimeError, match="already running"):
            await scenario.start(AnomalyStartRequest())


# ---------------------------------------------------------------------------

class TestStopSuccess:
    @pytest.mark.asyncio
    async def test_calls_remove_latency(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 88

        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_network.remove_latency.assert_called_once_with(88)

    @pytest.mark.asyncio
    async def test_status_becomes_idle(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 88

        await scenario.start(AnomalyStartRequest())
        info = await scenario.stop()
        assert info.status == AnomalyStatus.IDLE

    @pytest.mark.asyncio
    async def test_pid_reset_after_stop(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 88

        await scenario.start(AnomalyStartRequest())
        await scenario.stop()
        assert scenario._pid == 0


# ---------------------------------------------------------------------------

class TestStopNotRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario):
        with pytest.raises(RuntimeError, match="not running"):
            await scenario.stop()


# ---------------------------------------------------------------------------

class TestStartErrorSetsStatus:
    @pytest.mark.asyncio
    async def test_no_pods_sets_error_status(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = []

        with pytest.raises(RuntimeError):
            await scenario.start(AnomalyStartRequest())

        assert scenario.info.status == AnomalyStatus.ERROR

    @pytest.mark.asyncio
    async def test_error_message_is_set(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = []

        with pytest.raises(RuntimeError):
            await scenario.start(AnomalyStartRequest())

        assert scenario.info.error_message is not None
