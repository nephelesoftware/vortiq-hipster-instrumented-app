from datetime import datetime

import pytest

from app.models import AnomalyInfo, AnomalyStartRequest, AnomalyStatus


class TestAnomalyStatus:
    def test_all_values_are_strings(self):
        for member in AnomalyStatus:
            assert isinstance(member.value, str)

    def test_enum_values(self):
        assert AnomalyStatus.IDLE == "idle"
        assert AnomalyStatus.RUNNING == "running"
        assert AnomalyStatus.ERROR == "error"
        assert AnomalyStatus.STOPPING == "stopping"


class TestAnomalyInfo:
    def _make(self, **kwargs):
        defaults = dict(
            id="test_scenario",
            name="Test Scenario",
            description="A test scenario",
            affected_services=["frontend"],
            expected_impact="Some impact",
        )
        defaults.update(kwargs)
        return AnomalyInfo(**defaults)

    def test_default_status_is_idle(self):
        info = self._make()
        assert info.status == AnomalyStatus.IDLE

    def test_default_started_at_is_none(self):
        info = self._make()
        assert info.started_at is None

    def test_default_error_message_is_none(self):
        info = self._make()
        assert info.error_message is None

    def test_default_parameters_empty_dict(self):
        info = self._make()
        assert info.parameters == {}

    def test_status_can_be_set(self):
        info = self._make(status=AnomalyStatus.RUNNING)
        assert info.status == AnomalyStatus.RUNNING

    def test_started_at_accepts_datetime(self):
        now = datetime.utcnow()
        info = self._make(started_at=now)
        assert info.started_at == now

    def test_parameters_stored_correctly(self):
        params = {"delay_ms": 800, "jitter_ms": 200}
        info = self._make(parameters=params)
        assert info.parameters == params

    def test_serialization_round_trip(self):
        info = self._make(status=AnomalyStatus.RUNNING, parameters={"k": "v"})
        data = info.model_dump()
        restored = AnomalyInfo(**data)
        assert restored.id == info.id
        assert restored.status == info.status
        assert restored.parameters == info.parameters

    def test_json_serialization(self):
        info = self._make()
        json_str = info.model_dump_json()
        assert "test_scenario" in json_str
        assert "idle" in json_str

    def test_affected_services_is_list(self):
        info = self._make(affected_services=["a", "b", "c"])
        assert len(info.affected_services) == 3

    def test_error_message_can_be_set(self):
        info = self._make(error_message="something went wrong")
        assert info.error_message == "something went wrong"


class TestAnomalyStartRequest:
    def test_default_parameters_empty(self):
        req = AnomalyStartRequest()
        assert req.parameters == {}

    def test_parameters_can_be_provided(self):
        req = AnomalyStartRequest(parameters={"delay_ms": 500})
        assert req.parameters["delay_ms"] == 500
