"""In-memory counters since the process started.

Deliberately simple (no database): these metrics feed the Demo V1
dashboard, and must NEVER be invented on the frontend side — if a metric
hasn't been measured yet, it must stay absent/None rather than show a
made-up number.
"""

import threading
import time

STATUTS_CONNUS = ("COMPLETE", "PARTIAL", "NOT_FOUND")


class MetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.monotonic()
        self.requests_total = 0
        self.status_counts = {statut: 0 for statut in STATUTS_CONNUS}
        self.errors_total = 0
        self._latences_secondes: list[float] = []

    def record_request(self, statut: str, latence_secondes: float) -> None:
        with self._lock:
            self.requests_total += 1
            if statut in self.status_counts:
                self.status_counts[statut] += 1
            self._latences_secondes.append(latence_secondes)

    def record_error(self) -> None:
        with self._lock:
            self.errors_total += 1

    def reset(self) -> None:
        """Tests only: resets the counters to zero to isolate each test
        from the process-wide shared singleton."""
        with self._lock:
            self._start_time = time.monotonic()
            self.requests_total = 0
            self.status_counts = {statut: 0 for statut in STATUTS_CONNUS}
            self.errors_total = 0
            self._latences_secondes = []

    def snapshot(self) -> dict:
        with self._lock:
            latence_moyenne = (
                sum(self._latences_secondes) / len(self._latences_secondes)
                if self._latences_secondes
                else None
            )
            return {
                "uptime_secondes": time.monotonic() - self._start_time,
                "requests_total": self.requests_total,
                "status_complete": self.status_counts["COMPLETE"],
                "status_partial": self.status_counts["PARTIAL"],
                "status_not_found": self.status_counts["NOT_FOUND"],
                "errors_total": self.errors_total,
                "latence_moyenne_secondes": latence_moyenne,
            }


# A single metrics store per process — consistent with "one set of
# metrics per container", no sharing across different containers.
metrics_store = MetricsStore()
