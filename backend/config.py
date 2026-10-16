"""Backend settings; no ML dependencies are required to start the server."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    data_dir: Path = PROJECT_ROOT / "data" / "projects"
    ml_mode: str = "demo"
    ml_timeout_seconds: float = 1200
    max_file_bytes: int = 10 * 1024 * 1024
    max_reference_chars: int = 120000
    max_files: int = 5
    cloud_api_key: str = field(default="", repr=False)
    cloud_base_url: str = "https://foundation-models.api.cloud.ru/v1"
    cloud_model: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        raw_origins = os.getenv("CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS))
        origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit frontend origins")
        mode = os.getenv("ML_MODE", "demo").lower()
        if mode not in {"demo", "cloud"}:
            raise ValueError("ML_MODE must be demo or cloud")
        data_dir = Path(os.getenv("PROJECT_DATA_DIR", str(PROJECT_ROOT / "data" / "projects")))
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        timeout = float(os.getenv("ML_TIMEOUT_SECONDS", "1200"))
        if timeout <= 0:
            raise ValueError("ML_TIMEOUT_SECONDS must be positive")
        return cls(
            cors_origins=origins, data_dir=data_dir, ml_mode=mode,
            ml_timeout_seconds=timeout,
            cloud_api_key=os.getenv("CLOUD_RU_API_KEY", ""),
            cloud_base_url=os.getenv("CLOUD_RU_BASE_URL", "https://foundation-models.api.cloud.ru/v1"),
            cloud_model=os.getenv("CLOUD_RU_MODEL", ""),
        )
