"""
Integration tests for the FastAPI app using the TestClient.

The K8sClient and NetworkChaos are mocked at module level so that importing
app.main does not attempt a real cluster connection.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import AnomalyInfo, AnomalyStatus


# ---------------------------------------------------------------------------
# Build a minimal set of mock anomalies that the app can use
# ---------------------------------------------------------------------------

def _make_info(anomaly_id: str, status: AnomalyStatus = AnomalyStatus.IDLE) -> AnomalyInfo:
    return AnomalyInfo(
        id=anomaly_id,
        name=f"Scenario {anomaly_id}",
        description="A test anomaly",
        affected_services=["frontend"],
        expected_impact="Some impact",
        status=status,
    )


def _make_anomaly_mock(anomaly_id: str, status: AnomalyStatus = AnomalyStatus.IDLE):
    mock = MagicMock()
    mock.info = _make_info(anomaly_id, status)

    async def start_side_effect(req):
        mock.info.status = AnomalyStatus.RUNNING
        return mock.info

    async def stop_side_effect():
        mock.info.status = AnomalyStatus.IDLE
        return mock.info

    mock.start = AsyncMock(side_effect=start_side_effect)
    mock.stop = AsyncMock(side_effect=stop_side_effect)
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_anomaly_registry():
    idle = _make_anomaly_mock("s01_test_idle", AnomalyStatus.IDLE)
    running = _make_anomaly_mock("s02_test_running", AnomalyStatus.RUNNING)
    return {
        "s01_test_idle": idle,
        "s02_test_running": running,
    }


@pytest.fixture
def test_client(mock_anomaly_registry, tmp_path):
    """Create a TestClient with mocked K8s/network and anomaly registry."""
    # Create a minimal static dir so StaticFiles doesn't fail
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>test</html>")

    with patch("app.main.K8sClient"), \
         patch("app.main.NetworkChaos"), \
         patch("app.main.get_all_anomalies", return_value=mock_anomaly_registry), \
         patch("app.main._static_dir", str(static_dir)):

        # Re-import to pick up patches
        import importlib
        import app.main as main_module
        importlib.reload(main_module)
        main_module.anomalies = mock_anomaly_registry
        main_module._static_dir = str(static_dir)

        from fastapi.testclient import TestClient as TC
        client = TC(main_module.app)
        yield client


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, test_client):
        res = test_client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/anomalies
# ---------------------------------------------------------------------------

class TestListAnomalies:
    def test_returns_list_of_anomalies(self, test_client, mock_anomaly_registry):
        res = test_client.get("/api/anomalies")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == len(mock_anomaly_registry)

    def test_all_have_required_fields(self, test_client):
        res = test_client.get("/api/anomalies")
        for item in res.json():
            assert "id" in item
            assert "name" in item
            assert "status" in item
            assert "affected_services" in item


# ---------------------------------------------------------------------------
# GET /api/anomalies/{id}
# ---------------------------------------------------------------------------

class TestGetAnomaly:
    def test_returns_specific_anomaly(self, test_client):
        res = test_client.get("/api/anomalies/s01_test_idle")
        assert res.status_code == 200
        assert res.json()["id"] == "s01_test_idle"

    def test_nonexistent_returns_404(self, test_client):
        res = test_client.get("/api/anomalies/does_not_exist")
        assert res.status_code == 404

    def test_running_anomaly_has_running_status(self, test_client):
        res = test_client.get("/api/anomalies/s02_test_running")
        assert res.status_code == 200
        assert res.json()["status"] == "running"


# ---------------------------------------------------------------------------
# POST /api/anomalies/{id}/start
# ---------------------------------------------------------------------------

class TestStartAnomaly:
    def test_start_idle_returns_200(self, test_client):
        res = test_client.post(
            "/api/anomalies/s01_test_idle/start",
            json={"parameters": {}},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "running"

    def test_start_already_running_returns_409(self, test_client, mock_anomaly_registry):
        # Make start() raise RuntimeError (already running)
        mock_anomaly_registry["s02_test_running"].start = AsyncMock(
            side_effect=RuntimeError("already running")
        )
        res = test_client.post("/api/anomalies/s02_test_running/start", json={})
        assert res.status_code == 409

    def test_start_nonexistent_returns_404(self, test_client):
        res = test_client.post("/api/anomalies/no_such_anomaly/start", json={})
        assert res.status_code == 404

    def test_start_propagates_500_on_unexpected_error(self, test_client, mock_anomaly_registry):
        mock_anomaly_registry["s01_test_idle"].start = AsyncMock(
            side_effect=Exception("unexpected crash")
        )
        res = test_client.post("/api/anomalies/s01_test_idle/start", json={})
        assert res.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/anomalies/{id}/stop
# ---------------------------------------------------------------------------

class TestStopAnomaly:
    def test_stop_running_returns_200(self, test_client):
        res = test_client.post("/api/anomalies/s02_test_running/stop")
        assert res.status_code == 200
        assert res.json()["status"] == "idle"

    def test_stop_idle_returns_409(self, test_client, mock_anomaly_registry):
        mock_anomaly_registry["s01_test_idle"].stop = AsyncMock(
            side_effect=RuntimeError("not running")
        )
        res = test_client.post("/api/anomalies/s01_test_idle/stop")
        assert res.status_code == 409

    def test_stop_nonexistent_returns_404(self, test_client):
        res = test_client.post("/api/anomalies/no_such_anomaly/stop")
        assert res.status_code == 404

    def test_stop_propagates_500_on_unexpected_error(self, test_client, mock_anomaly_registry):
        mock_anomaly_registry["s02_test_running"].stop = AsyncMock(
            side_effect=Exception("unexpected crash")
        )
        res = test_client.post("/api/anomalies/s02_test_running/stop")
        assert res.status_code == 500
