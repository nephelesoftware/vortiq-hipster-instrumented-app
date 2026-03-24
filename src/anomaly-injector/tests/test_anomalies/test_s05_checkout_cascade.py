import pytest
from unittest.mock import MagicMock

from app.anomalies.s05_checkout_cascade import CheckoutCascade
from app.models import AnomalyStartRequest, AnomalyStatus


def _make_pod(name="checkoutservice-abc"):
    pod = MagicMock()
    pod.metadata.name = name
    return pod


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return CheckoutCascade(mock_k8s, mock_network)


class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s05_checkout_cascade"

    def test_name_contains_checkout(self, scenario):
        assert "Checkout" in scenario.info.name

    def test_affected_services_contains_checkout(self, scenario):
        assert "checkoutservice" in scenario.info.affected_services

    def test_affected_services_multi_hop(self, scenario):
        svcs = scenario.info.affected_services
        assert "paymentservice" in svcs
        assert "shippingservice" in svcs
        assert "emailservice" in svcs
        assert "cartservice" in svcs
        assert "currencyservice" in svcs

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE

    def test_default_parameters(self, scenario):
        assert scenario.info.parameters.get("delay_ms") == 1200
        assert scenario.info.parameters.get("jitter_ms") == 300


class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_gets_checkoutservice_pods(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 99

        await scenario.start(AnomalyStartRequest())

        mock_k8s.get_pods.assert_called_once_with("hipster", "app=checkoutservice")

    @pytest.mark.asyncio
    async def test_injects_default_latency(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 77

        await scenario.start(AnomalyStartRequest())

        mock_network.add_latency.assert_called_once_with(77, 1200, 300)

    @pytest.mark.asyncio
    async def test_custom_params_passed_to_add_latency(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 55

        await scenario.start(AnomalyStartRequest(parameters={"delay_ms": 500, "jitter_ms": 100}))

        mock_network.add_latency.assert_called_once_with(55, 500, 100)

    @pytest.mark.asyncio
    async def test_status_becomes_running(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 42

        info = await scenario.start(AnomalyStartRequest())
        assert info.status == AnomalyStatus.RUNNING


class TestStartAlreadyRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 42

        await scenario.start(AnomalyStartRequest())

        with pytest.raises(RuntimeError, match="already running"):
            await scenario.start(AnomalyStartRequest())


class TestStopSuccess:
    @pytest.mark.asyncio
    async def test_calls_remove_latency(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 33

        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_network.remove_latency.assert_called_once_with(33)

    @pytest.mark.asyncio
    async def test_status_becomes_idle(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 33

        await scenario.start(AnomalyStartRequest())
        info = await scenario.stop()
        assert info.status == AnomalyStatus.IDLE

    @pytest.mark.asyncio
    async def test_pid_reset_after_stop(self, scenario, mock_k8s, mock_network):
        mock_k8s.get_pods.return_value = [_make_pod()]
        mock_k8s.get_container_id.return_value = "abc123"
        mock_network.get_container_pid.return_value = 33

        await scenario.start(AnomalyStartRequest())
        await scenario.stop()
        assert scenario._pid == 0


class TestStopNotRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario):
        with pytest.raises(RuntimeError, match="not running"):
            await scenario.stop()


class TestStartErrorSetsStatus:
    @pytest.mark.asyncio
    async def test_no_pods_sets_error_status(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = []

        with pytest.raises(RuntimeError):
            await scenario.start(AnomalyStartRequest())

        assert scenario.info.status == AnomalyStatus.ERROR
