import logging
import os
import subprocess

logger = logging.getLogger(__name__)


class NetworkChaos:
    def get_container_pid(self, container_id: str) -> int:
        """Find the PID of a container by scanning /proc cgroup entries."""
        short_id = container_id[:12]
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/cgroup") as f:
                    if short_id in f.read():
                        return int(pid)
            except (IOError, OSError):
                continue
        raise ValueError(f"No process found for container {short_id}")

    def add_latency(self, pid: int, delay_ms: int, jitter_ms: int = 10) -> None:
        """Inject network latency into a container's network namespace via tc netem."""
        try:
            subprocess.run(
                [
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "--",
                    "tc",
                    "qdisc",
                    "add",
                    "dev",
                    "eth0",
                    "root",
                    "netem",
                    "delay",
                    f"{delay_ms}ms",
                    f"{jitter_ms}ms",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Added %dms ± %dms latency to pid %d", delay_ms, jitter_ms, pid)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to add latency to pid {pid}: {e.stderr.strip()}"
            ) from e

    def remove_latency(self, pid: int) -> None:
        """Remove tc qdisc rules from a container's network namespace."""
        try:
            subprocess.run(
                [
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "--",
                    "tc",
                    "qdisc",
                    "del",
                    "dev",
                    "eth0",
                    "root",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Removed tc qdisc rules from pid %d", pid)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else ""
            # If qdisc doesn't exist it's fine — already clean
            if "RTNETLINK answers: No such file or directory" in stderr or "Cannot find device" in stderr:
                logger.warning(
                    "tc qdisc not found on pid %d — already removed or never applied", pid
                )
                return
            raise RuntimeError(
                f"Failed to remove tc qdisc from pid {pid}: {stderr}"
            ) from e

    def add_packet_loss(self, pid: int, loss_percent: int) -> None:
        """Inject packet loss into a container's network namespace via tc netem."""
        try:
            subprocess.run(
                [
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "--",
                    "tc",
                    "qdisc",
                    "add",
                    "dev",
                    "eth0",
                    "root",
                    "netem",
                    "loss",
                    f"{loss_percent}%",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Added %d%% packet loss to pid %d", loss_percent, pid)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to add packet loss to pid {pid}: {e.stderr.strip()}"
            ) from e
