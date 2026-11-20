import subprocess
from pathlib import Path

import pytest

from app.core.config import Settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_provider_database_urls_keep_encoded_credentials_and_use_async_driver(scheme):
    settings = Settings(database_url=f"{scheme}://user:p%40ss%3Aword@host/db?sslmode=require")
    assert settings.database_url == "postgresql+asyncpg://user:p%40ss%3Aword@host/db?ssl=require"


def test_provider_database_url_does_not_weaken_production_validation():
    with pytest.raises(ValueError):
        Settings(
            database_url="postgresql://user:pw@host/db", app_env="production", cookie_secure=False
        )


def test_render_blueprint_uses_liveness_probe_and_valid_startup_script():
    render_yaml = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /api/v1/health/live" in render_yaml
    script = ROOT / "scripts" / "start-render.sh"
    result = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
