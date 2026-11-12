"""Admin configuration supports the new names and existing deployments."""
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("values, expected", [
    ({"ADMIN_EMAIL": "admin@example.org", "ADMIN_PASSWORD": "new-secret"}, "admin@example.org:new-secret"),
    ({"SUPERUSER_EMAIL": "legacy@example.org", "SUPERUSER_PASSWORD": "old-secret"}, "legacy@example.org:old-secret"),
    ({"ADMIN_EMAIL": "admin@example.org", "ADMIN_PASSWORD": "new-secret", "SUPERUSER_EMAIL": "legacy@example.org", "SUPERUSER_PASSWORD": "old-secret"}, "admin@example.org:new-secret"),
])
def test_admin_environment_names(values, expected):
    env = {key: value for key, value in os.environ.items() if not key.startswith(("ADMIN_", "SUPERUSER_"))}
    env.update(values)
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; print(settings.admin_email + ':' + settings.admin_password)"],
        env=env, check=True, capture_output=True, text=True,
    )
    assert result.stdout.strip() == expected
