import pytest

from app.anomalies.s04_currency_outage import CurrencyOutage
from app.models import AnomalyStartRequest, AnomalyStatus


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return CurrencyOutage(mock_k8s, mock_network)


class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s04_currency_outage"

    def test_name_contains_currency(self, scenario):
        assert "Currency" in scenario.info.name

    def test_affected_services(self, scenario):
        svcs = scenario.info.affected_services
        assert "currencyservice" in svcs
        assert "frontend" in svcs
        assert "checkoutservice" in svcs

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE


class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_reads_current_replicas(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 2

        await scenario.start(AnomalyStartRequest())

        mock_k8s.get_deployment_replicas.assert_called_once_with("hipster", "currencyservice")

    @pytest.mark.asyncio
    async def test_scales_to_zero(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1

        await scenario.start(AnomalyStartRequest())

        mock_k8s.scale_deployment.assert_called_once_with("hipster", "currencyservice", 0)

    @pytest.mark.asyncio
    async def test_stores_original_replicas(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 3

        await scenario.start(AnomalyStartRequest())

        assert scenario._original_replicas == 3

    @pytest.mark.asyncio
    async def test_status_becomes_running(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1

        info = await scenario.start(AnomalyStartRequest())
        assert info.status == AnomalyStatus.RUNNING


class TestStartAlreadyRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1
        await scenario.start(AnomalyStartRequest())

        with pytest.raises(RuntimeError, match="already running"):
            await scenario.start(AnomalyStartRequest())


class TestStopSuccess:
    @pytest.mark.asyncio
    async def test_restores_replicas(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 2
        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_k8s.scale_deployment.assert_called_with("hipster", "currencyservice", 2)

    @pytest.mark.asyncio
    async def test_defaults_to_one_if_original_was_zero(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 0
        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_k8s.scale_deployment.assert_called_with("hipster", "currencyservice", 1)

    @pytest.mark.asyncio
    async def test_status_becomes_idle(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1
        await scenario.start(AnomalyStartRequest())
        info = await scenario.stop()
        assert info.status == AnomalyStatus.IDLE


class TestStopNotRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario):
        with pytest.raises(RuntimeError, match="not running"):
            await scenario.stop()


class TestStartErrorSetsStatus:
    @pytest.mark.asyncio
    async def test_scale_error_sets_error_status(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1
        mock_k8s.scale_deployment.side_effect = RuntimeError("k8s error")

        with pytest.raises(RuntimeError):
            await scenario.start(AnomalyStartRequest())

        assert scenario.info.status == AnomalyStatus.ERROR
        assert scenario.info.error_message is not None
