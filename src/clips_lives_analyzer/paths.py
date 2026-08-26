from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    config: Path
    jobs: Path
    results: Path
    logs: Path

    @classmethod
    def default(cls) -> "AppPaths":
        root = Path(user_data_dir("ClipsLivesAnalyzer", "InsanoToni"))
        return cls(
            root=root,
            database=root / "queue.sqlite3",
            config=root / "config.json",
            jobs=root / "jobs",
            results=root / "results",
            logs=root / "logs",
        )

    def ensure(self) -> None:
        for path in (self.root, self.jobs, self.results, self.logs):
            path.mkdir(parents=True, exist_ok=True)
