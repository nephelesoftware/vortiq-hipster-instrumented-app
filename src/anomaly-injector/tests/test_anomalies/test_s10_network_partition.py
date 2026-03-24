import pytest

from app.anomalies.s10_network_partition import NetworkPartition
from app.models import AnomalyStartRequest, AnomalyStatus


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return NetworkPartition(mock_k8s, mock_network)


class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s10_network_partition"

    def test_name_contains_partition(self, scenario):
        assert "Partition" in scenario.info.name or "partition" in scenario.info.name.lower()

    def test_affected_services_not_empty(self, scenario):
        assert len(scenario.info.affected_services) > 0

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE

    def test_default_parameters(self, scenario):
        assert scenario.info.parameters.get("target_service") == "productcatalogservice"


class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_reads_current_replicas_for_default_target(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1

        await scenario.start(AnomalyStartRequest())

        mock_k8s.get_deployment_replicas.assert_called_once_with(
            "hipster", "productcatalogservice"
        )

    @pytest.mark.asyncio
    async def test_scales_default_target_to_zero(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1

        await scenario.start(AnomalyStartRequest())

        mock_k8s.scale_deployment.assert_called_once_with(
            "hipster", "productcatalogservice", 0
        )

    @pytest.mark.asyncio
    async def test_custom_target_service(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 2

        await scenario.start(
            AnomalyStartRequest(parameters={"target_service": "currencyservice"})
        )

        mock_k8s.scale_deployment.assert_called_once_with("hipster", "currencyservice", 0)

    @pytest.mark.asyncio
    async def test_affected_services_updated_dynamically(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1

        await scenario.start(
            AnomalyStartRequest(parameters={"target_service": "cartservice"})
        )

        assert "cartservice" in scenario.info.affected_services

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

        mock_k8s.scale_deployment.assert_called_with(
            "hipster", "productcatalogservice", 2
        )

    @pytest.mark.asyncio
    async def test_defaults_to_one_when_original_zero(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 0
        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_k8s.scale_deployment.assert_called_with(
            "hipster", "productcatalogservice", 1
        )

    @pytest.mark.asyncio
    async def test_restores_custom_target(self, scenario, mock_k8s):
        mock_k8s.get_deployment_replicas.return_value = 1
        await scenario.start(
            AnomalyStartRequest(parameters={"target_service": "shippingservice"})
        )
        await scenario.stop()

        mock_k8s.scale_deployment.assert_called_with("hipster", "shippingservice", 1)

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
