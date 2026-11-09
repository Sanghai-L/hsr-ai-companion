import subprocess
import sys

from companion.services.context import Context
from companion.services.registry import Registry


def test_operator_help_is_read_only_and_every_named_command_exists(tmp_path):
    path = tmp_path/"untouched"
    result = Registry(Context(path, offline=True)).invoke("local_help", {})
    assert result.status == "success" and result.data["executed"] is False and not path.exists()
    assert result.data["sections"]["diagnostics"]["automatic_upload"] is False
    assert result.data["sections"]["install"]["uninstall_preserves_personal"]
    for command in ("diagnostics-plan", "diagnostics-export", "install-program", "configure-codex", "recover-program", "rollback-program", "uninstall-program", "confirm-update"):
        child = subprocess.run([sys.executable, "-m", "companion", command, "--help"], capture_output=True, timeout=10)
        assert child.returncode == 0, command
