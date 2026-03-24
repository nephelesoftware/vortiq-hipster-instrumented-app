import pytest

from app.anomalies.s06_memory_leak import MemoryLeak, JOB_NAME
from app.models import AnomalyStartRequest, AnomalyStatus


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return MemoryLeak(mock_k8s, mock_network)


class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s06_memory_leak"

    def test_name_contains_memory(self, scenario):
        assert "Memory" in scenario.info.name or "OOM" in scenario.info.name

    def test_affected_services(self, scenario):
        assert "productcatalogservice" in scenario.info.affected_services

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE

    def test_default_parameters(self, scenario):
        params = scenario.info.parameters
        assert params.get("memory_mb") == 450


class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_creates_memory_job(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        await scenario.start(AnomalyStartRequest())

        mock_k8s.create_job.assert_called_once()
        manifest = mock_k8s.create_job.call_args[0][1]
        assert manifest["metadata"]["name"] == JOB_NAME

    @pytest.mark.asyncio
    async def test_job_uses_stress_image(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        await scenario.start(AnomalyStartRequest())

        manifest = mock_k8s.create_job.call_args[0][1]
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "stress" in container["image"]

    @pytest.mark.asyncio
    async def test_job_has_memory_limit(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        await scenario.start(AnomalyStartRequest())

        manifest = mock_k8s.create_job.call_args[0][1]
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "512Mi" in container["resources"]["limits"]["memory"]

    @pytest.mark.asyncio
    async def test_custom_memory_mb(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False

        await scenario.start(AnomalyStartRequest(parameters={"memory_mb": 300}))

        manifest = mock_k8s.create_job.call_args[0][1]
        args = manifest["spec"]["template"]["spec"]["containers"][0]["args"]
        assert "300M" in args

    @pytest.mark.asyncio
    async def test_skip_create_when_job_exists(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = True

        await scenario.start(AnomalyStartRequest())

        mock_k8s.create_job.assert_not_called()

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
        mock_k8s.job_exists.side_effect = [False, True]
        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_k8s.delete_job.assert_called_once_with("hipster", JOB_NAME)

    @pytest.mark.asyncio
    async def test_skip_delete_when_job_gone(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
        await scenario.start(AnomalyStartRequest())
        await scenario.stop()

        mock_k8s.delete_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_becomes_idle(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
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
    async def test_create_error_sets_error_status(self, scenario, mock_k8s):
        mock_k8s.job_exists.return_value = False
        mock_k8s.create_job.side_effect = RuntimeError("api error")

        with pytest.raises(RuntimeError):
            await scenario.start(AnomalyStartRequest())

        assert scenario.info.status == AnomalyStatus.ERROR
