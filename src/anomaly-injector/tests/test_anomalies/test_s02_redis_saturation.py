import pytest
from unittest.mock import MagicMock, call

from app.anomalies.s02_redis_saturation import RedisSaturation, JOB_NAME
from app.models import AnomalyStartRequest, AnomalyStatus


def _make_pod(name="redis-cart-abc"):
    pod = MagicMock()
    pod.metadata.name = name
    return pod


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return RedisSaturation(mock_k8s, mock_network)


class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s02_redis_saturation"

    def test_name_contains_redis(self, scenario):
        assert "Redis" in scenario.info.name

    def test_affected_services(self, scenario):
        svcs = scenario.info.affected_services
        assert "redis-cart" in svcs
        assert "cartservice" in svcs
        assert "checkoutservice" in svcs

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE


class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_creates_job_when_not_existing(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        await scenario.start(AnomalyStartRequest())

        mock_k8s.create_job.assert_called_once()
        args = mock_k8s.create_job.call_args
        assert args[0][0] == "hipster"

    @pytest.mark.asyncio
    async def test_skips_create_when_job_exists(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = True

        await scenario.start(AnomalyStartRequest())

        mock_k8s.create_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_job_manifest_has_correct_name(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        await scenario.start(AnomalyStartRequest())

        manifest = mock_k8s.create_job.call_args[0][1]
        assert manifest["metadata"]["name"] == JOB_NAME

    @pytest.mark.asyncio
    async def test_status_becomes_running(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        info = await scenario.start(AnomalyStartRequest())
        assert info.status == AnomalyStatus.RUNNING


class TestStartAlreadyRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
        await scenario.start(AnomalyStartRequest())

        with pytest.raises(RuntimeError, match="already running"):
            await scenario.start(AnomalyStartRequest())


class TestStopSuccess:
    @pytest.mark.asyncio
    async def test_deletes_job_when_exists(self, scenario, mock_k8s):
        mock_k8s.job_exists.side_effect = [False, True]  # start: not exists; stop: exists
        mock_k8s.get_pods.return_value = [_make_pod()]

        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_k8s.delete_job.assert_called_once_with("hipster", JOB_NAME)

    @pytest.mark.asyncio
    async def test_skip_delete_when_job_gone(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
        mock_k8s.get_pods.return_value = []

        await scenario.start(AnomalyStartRequest())
        # Should not raise even if job already gone
        await scenario.stop()

        mock_k8s.delete_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_becomes_idle(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
        mock_k8s.get_pods.return_value = []

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
    async def test_create_job_exception_sets_error(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
        mock_k8s.create_job.side_effect = RuntimeError("k8s error")

        with pytest.raises(RuntimeError):
            await scenario.start(AnomalyStartRequest())

        assert scenario.info.status == AnomalyStatus.ERROR
