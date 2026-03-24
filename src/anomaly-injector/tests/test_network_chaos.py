import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.network_chaos import NetworkChaos


@pytest.fixture
def chaos():
    return NetworkChaos()


# ---------------------------------------------------------------------------
# get_container_pid
# ---------------------------------------------------------------------------

class TestGetContainerPid:
    def test_found_returns_pid(self, chaos):
        container_id = "abc123def456abcd"
        short_id = container_id[:12]  # "abc123def456"

        with patch("os.listdir", return_value=["1", "99", "not-a-pid", "200"]):
            def fake_open(path, *args, **kwargs):
                if "/proc/99/cgroup" in path:
                    return mock_open(read_data=f"11:blkio:/kubepods/{short_id}\n")()
                m = MagicMock()
                m.__enter__ = lambda s: s
                m.__exit__ = MagicMock(return_value=False)
                m.read.return_value = "unrelated content"
                return m

            with patch("builtins.open", side_effect=fake_open):
                pid = chaos.get_container_pid(container_id)
                assert pid == 99

    def test_not_found_raises_value_error(self, chaos):
        with patch("os.listdir", return_value=["1", "2"]):
            with patch("builtins.open", mock_open(read_data="unrelated")):
                with pytest.raises(ValueError, match="No process found"):
                    chaos.get_container_pid("deadbeef12345678")

    def test_io_error_skips_pid(self, chaos):
        with patch("os.listdir", return_value=["1"]):
            with patch("builtins.open", side_effect=IOError("permission denied")):
                with pytest.raises(ValueError, match="No process found"):
                    chaos.get_container_pid("abc123def456aaaa")

    def test_non_digit_entries_skipped(self, chaos):
        with patch("os.listdir", return_value=["net", "sys", "tty"]):
            with pytest.raises(ValueError):
                chaos.get_container_pid("abc123def456aaaa")


# ---------------------------------------------------------------------------
# add_latency
# ---------------------------------------------------------------------------

class TestAddLatency:
    def test_success_calls_subprocess(self, chaos):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            chaos.add_latency(12345, 800, 200)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "nsenter" in args
        assert "800ms" in args
        assert "200ms" in args
        assert "12345" in [str(a) for a in args]

    def test_subprocess_error_raises_runtime_error(self, chaos):
        with patch("subprocess.run") as mock_run:
            err = subprocess.CalledProcessError(1, "nsenter", stderr="RTNETLINK error")
            mock_run.side_effect = err

            with pytest.raises(RuntimeError, match="Failed to add latency"):
                chaos.add_latency(12345, 800, 200)

    def test_default_jitter(self, chaos):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            chaos.add_latency(12345, 500)

        args = mock_run.call_args[0][0]
        assert "10ms" in args  # default jitter


# ---------------------------------------------------------------------------
# remove_latency
# ---------------------------------------------------------------------------

class TestRemoveLatency:
    def test_success_calls_subprocess(self, chaos):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            chaos.remove_latency(12345)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "nsenter" in args
        assert "del" in args

    def test_rtnetlink_not_found_does_not_raise(self, chaos):
        with patch("subprocess.run") as mock_run:
            err = subprocess.CalledProcessError(2, "nsenter")
            err.stderr = "RTNETLINK answers: No such file or directory"
            mock_run.side_effect = err

            # Should not raise
            chaos.remove_latency(12345)

    def test_other_subprocess_error_raises_runtime_error(self, chaos):
        with patch("subprocess.run") as mock_run:
            err = subprocess.CalledProcessError(1, "nsenter")
            err.stderr = "some unexpected error"
            mock_run.side_effect = err

            with pytest.raises(RuntimeError, match="Failed to remove tc qdisc"):
                chaos.remove_latency(12345)


# ---------------------------------------------------------------------------
# add_packet_loss
# ---------------------------------------------------------------------------

class TestAddPacketLoss:
    def test_success_calls_subprocess(self, chaos):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            chaos.add_packet_loss(12345, 30)

        args = mock_run.call_args[0][0]
        assert "30%" in args
        assert "loss" in args

    def test_subprocess_error_raises_runtime_error(self, chaos):
        with patch("subprocess.run") as mock_run:
            err = subprocess.CalledProcessError(1, "nsenter", stderr="error")
            mock_run.side_effect = err

            with pytest.raises(RuntimeError, match="Failed to add packet loss"):
                chaos.add_packet_loss(12345, 30)
