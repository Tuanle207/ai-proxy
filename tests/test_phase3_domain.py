"""Phase 3 tests: provider-scoped accounts/paths, providers config map, data-layout script."""

from __future__ import annotations

from pathlib import Path

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.config import Settings
from ai_proxy.core.models import TaskKind, TaskRequest
from ai_proxy.core.paths import DataPaths
from scripts.migrate_data_layout import main as migrate_layout


def test_paths_provider_scoping(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path)
    assert paths.accounts_file("google_flow") == (
        tmp_path / "providers" / "google_flow" / "accounts.yaml"
    )
    assert paths.storage_state_file("google_flow", "A@B.com") == (
        tmp_path / "providers" / "google_flow" / "sessions" / "a@b.com" / "storage_state.json"
    )
    assert paths.storage_state_file("perplexity", "A@B.com").parts[-4] == "perplexity"


def test_accounts_are_provider_scoped(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path)
    flow = AccountManager(paths, "google_flow")
    flow.add("shared@example.com")
    px = AccountManager(paths, "perplexity")
    assert px.list_accounts() == []  # no cross-provider leak (blocker 1.2.1)
    flow_state = paths.storage_state_file("google_flow", "shared@example.com")
    px_state = paths.storage_state_file("perplexity", "shared@example.com")
    assert flow_state != px_state  # blocker 1.2.2


def test_providers_config_from_yaml_and_env(
    tmp_path: Path, monkeypatch
) -> None:
    import os

    config = tmp_path / "config.yaml"
    config.write_text(
        "providers:\n  google_flow:\n    overlay_logo: true\n    logo_path: /tmp/x.png\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_PROXY_CONFIG_FILE", str(config))
    monkeypatch.setenv("AI_PROXY_GOOGLE_FLOW_OVERLAY_LOGO", "false")

    settings = Settings(data_dir=str(tmp_path / "data"))
    flow = settings.provider_settings("google_flow")
    assert flow["overlay_logo"] is False  # env wins over YAML
    assert flow["logo_path"] == "/tmp/x.png"  # YAML key survives
    assert settings.default_provider == "google_flow"
    assert not os.environ.get("AI_PROXY_LOGO_PATH")  # sanity: core prefix untouched


def test_flow_keys_left_core_config() -> None:
    names = set(Settings.model_fields)
    assert "overlay_logo" not in names
    assert "logo_path" not in names
    assert "delete_project_after_job" not in names
    assert "default_provider" in names
    assert "providers" in names


def test_task_request_flow_params_in_params_dict() -> None:
    request = TaskRequest(
        provider="google_flow",
        kind=TaskKind.IMAGE,
        prompt="a red apple",
        count=2,
        params={"model": "nano-banana", "aspect_ratio": "16:9"},
    )
    assert request.kind is TaskKind.IMAGE
    assert request.params["aspect_ratio"] == "16:9"
    assert not hasattr(request, "model") and not hasattr(request, "aspect_ratio")


def test_migrate_data_layout_idempotent(tmp_path: Path, capsys) -> None:
    root = tmp_path / "data"
    (root / "sessions" / "user@example.com").mkdir(parents=True)
    (root / "accounts.yaml").write_text("user@example.com: {}\n", encoding="utf-8")
    state = root / "sessions" / "user@example.com" / "storage_state.json"
    state.write_text('{"cookies": []}', encoding="utf-8")

    code = migrate_layout(["--data-dir", str(root)])  # real run
    assert code == 0
    new_accounts = root / "providers" / "google_flow" / "accounts.yaml"
    new_state = (
        root / "providers" / "google_flow" / "sessions" / "user@example.com" / "storage_state.json"
    )
    assert new_accounts.is_file() and not (root / "accounts.yaml").exists()
    assert new_state.read_text(encoding="utf-8") == '{"cookies": []}'
    assert not (root / "sessions").exists()

    migrate_layout(["--data-dir", str(root)])  # idempotent re-run
    out = capsys.readouterr().out
    assert "[skip]" not in out  # nothing left at the old locations at all
    assert new_accounts.is_file()
