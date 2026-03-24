import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.anomalies.s03_payment_flapping import PaymentFlapping, FLAP_INTERVAL_SECONDS
from app.models import AnomalyStartRequest, AnomalyStatus


def _make_pod(name="paymentservice-xyz"):
    pod = MagicMock()
    pod.metadata.name = name
    return pod


@pytest.fixture
def scenario(mock_k8s, mock_network):
    return PaymentFlapping(mock_k8s, mock_network)


class TestBuildInfo:
    def test_id(self, scenario):
        assert scenario.info.id == "s03_payment_flapping"

    def test_name_contains_flapping(self, scenario):
        assert "Flapping" in scenario.info.name or "flapping" in scenario.info.name.lower()

    def test_affected_services(self, scenario):
        svcs = scenario.info.affected_services
        assert "paymentservice" in svcs
        assert "checkoutservice" in svcs

    def test_initial_status_idle(self, scenario):
        assert scenario.info.status == AnomalyStatus.IDLE


class TestStartSuccess:
    @pytest.mark.asyncio
    async def test_creates_background_task(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = [_make_pod()]

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
            try:
                await scenario.start(AnomalyStartRequest())
            except asyncio.CancelledError:
                pass

        assert scenario._flap_task is not None

    @pytest.mark.asyncio
    async def test_status_becomes_running(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = [_make_pod()]

        # We patch sleep to prevent the loop from blocking
        with patch("asyncio.sleep", return_value=None):
            info = await scenario.start(AnomalyStartRequest())
        assert info.status == AnomalyStatus.RUNNING


class TestStartAlreadyRunning:
    @pytest.mark.asyncio
    async def test_raises_runtime_error(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = [_make_pod()]

        with patch("asyncio.sleep", return_value=None):
            await scenario.start(AnomalyStartRequest())

        with pytest.raises(RuntimeError, match="already running"):
            await scenario.start(AnomalyStartRequest())


class TestStopSuccess:
    @pytest.mark.asyncio
    async def test_cancels_task(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = [_make_pod()]

        with patch("asyncio.sleep", return_value=None):
            await scenario.start(AnomalyStartRequest())

        await scenario.stop()
        assert scenario._flap_task is None

    @pytest.mark.asyncio
    async def test_status_becomes_idle(self, scenario, mock_k8s):
        mock_k8s.get_pods.return_value = [_make_pod()]

        with patch("asyncio.sleep", return_value=None):
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
    async def test_task_creation_succeeds_but_flap_exceptions_are_logged(
        self, scenario, mock_k8s
    ):
        """The flap loop should swallow non-CancelledError exceptions."""
        mock_k8s.get_pods.side_effect = RuntimeError("k8s unavailable")

        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
            await scenario.start(AnomalyStartRequest())
            # Give the task a chance to run one iteration
            await asyncio.sleep(0)

        # Status should still be RUNNING — the loop catches exceptions itself
        assert scenario.info.status == AnomalyStatus.RUNNING
        await scenario.stop()
