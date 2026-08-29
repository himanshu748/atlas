"""Behavioral tests for the disposable Google Cloud deployment scripts.

The scripts run against a recording ``gcloud`` executable. No cloud account or
network access is used, but every command, argument and endpoint override is
captured so the deployment safety contract is exercised end to end.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


PROJECT = "atlas-agentic-hack-2026-v2"
BILLING_ACCOUNT = "ABCDEF-ABCDEF-ABCDEF"
ATLAS_ROOT = Path(__file__).resolve().parents[1]
INFRA = ATLAS_ROOT / "infra"


@pytest.fixture
def fake_gcloud(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "gcloud.jsonl"
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_GCLOUD_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "args": args,
        "modelarmor_endpoint": os.environ.get(
            "CLOUDSDK_API_ENDPOINT_OVERRIDES_MODELARMOR", ""
        ),
    }) + "\\n")

joined = " ".join(args)
if args[:2] == ["auth", "list"]:
    print(os.environ.get("FAKE_ACTIVE_ACCOUNT", "deployer@example.com"))
elif args[:2] == ["projects", "describe"]:
    if "projectNumber" in joined:
        print("123456789012")
    elif "lifecycleState" in joined:
        print(os.environ.get("FAKE_PROJECT_STATE", "ACTIVE"))
elif args[:3] == ["billing", "accounts", "describe"]:
    print("True")
elif args[:3] == ["billing", "projects", "describe"]:
    value = os.environ.get(
        "FAKE_LINKED_BILLING", "billingAccounts/ABCDEF-ABCDEF-ABCDEF"
    )
    print(value)
elif args[:3] == ["billing", "budgets", "list"]:
    print(os.environ.get("FAKE_EXISTING_BUDGET", ""))
elif args[:3] == ["run", "services", "describe"]:
    print("https://atlas-console-test-uc.a.run.app")
elif "describe" in args:
    sys.exit(1)
""",
        encoding="utf-8",
    )
    gcloud.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_GCLOUD_LOG": str(log_path),
        }
    )
    return env, log_path


def run_script(
    name: str,
    args: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(INFRA / name), *args],
        cwd=ATLAS_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def commands(log_path: Path) -> list[dict[str, object]]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines()]


def has_command(recorded: list[dict[str, object]], *parts: str) -> bool:
    return any(all(part in entry["args"] for part in parts) for entry in recorded)


def command_with(recorded: list[dict[str, object]], *prefix: str) -> list[str]:
    for entry in recorded:
        args = entry["args"]
        if args[: len(prefix)] == list(prefix):
            return args
    raise AssertionError(f"no command with prefix {prefix!r}: {recorded!r}")


def test_setup_links_billing_and_provisions_only_the_used_runtime(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud
    env["FAKE_LINKED_BILLING"] = ""

    result = run_script("setup_gcp.sh", [PROJECT, BILLING_ACCOUNT], env)

    assert result.returncode == 0, result.stdout + result.stderr
    recorded = commands(log_path)
    assert has_command(
        recorded,
        "billing",
        "projects",
        "describe",
        PROJECT,
    )
    assert has_command(
        recorded,
        "billing",
        "projects",
        "link",
        PROJECT,
        f"--billing-account={BILLING_ACCOUNT}",
    )
    assert not has_command(recorded, "config", "set", "project")

    enabled = command_with(recorded, "services", "enable")
    assert "iam.googleapis.com" in enabled
    assert "cloudtasks.googleapis.com" not in enabled

    created_accounts = [
        entry["args"][3]
        for entry in recorded
        if entry["args"][:3] == ["iam", "service-accounts", "create"]
    ]
    assert created_accounts == ["atlas-orchestrator", "atlas-builder"]
    assert has_command(recorded, "roles/run.builder")
    assert has_command(recorded, "roles/iam.serviceAccountUser")
    assert has_command(recorded, "atlas-events")
    assert not has_command(recorded, "atlas-work")

    armor_creates = [
        entry
        for entry in recorded
        if entry["args"][:4] == ["model-armor", "templates", "create", "atlas-ingress-strict"]
    ]
    assert len(armor_creates) == 1
    assert armor_creates[0]["modelarmor_endpoint"] == (
        "https://modelarmor.us.rep.googleapis.com/"
    )
    armor_args = armor_creates[0]["args"]
    assert "--location=us" in armor_args
    assert "--pi-and-jailbreak-filter-settings-confidence-level=low-and-above" in armor_args


def test_setup_refuses_any_project_except_the_disposable_project(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud

    result = run_script(
        "setup_gcp.sh",
        ["shared-production-project", BILLING_ACCOUNT],
        env,
    )

    assert result.returncode != 0
    assert "atlas-agentic-hack-2026-v2" in result.stderr
    assert commands(log_path) == []


def test_deploy_is_private_uses_separate_model_region_and_bounded_capacity(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud

    result = run_script("deploy.sh", [PROJECT], env)

    assert result.returncode == 0, result.stdout + result.stderr
    recorded = commands(log_path)
    deploy = command_with(recorded, "run", "deploy", "atlas-console")
    assert "--region=us-central1" in deploy
    assert "--no-allow-unauthenticated" in deploy
    assert "--concurrency=1" in deploy
    assert "--min-instances=0" in deploy
    assert "--max-instances=1" in deploy
    assert "--cpu-throttling" in deploy
    assert "--no-cpu-boost" in deploy
    assert "--build-service-account=projects/atlas-agentic-hack-2026-v2/serviceAccounts/atlas-builder@atlas-agentic-hack-2026-v2.iam.gserviceaccount.com" in deploy
    assert f"--source={ATLAS_ROOT}" in deploy

    env_flag = next(arg for arg in deploy if arg.startswith("--set-env-vars="))
    assert "GOOGLE_CLOUD_LOCATION=us" in env_flag
    assert "GOOGLE_GENAI_USE_VERTEXAI=true" in env_flag
    assert "ATLAS_RUN_BUDGET_USD=5" in env_flag

    scheduler = command_with(
        recorded,
        "scheduler",
        "jobs",
        "create",
        "http",
        "atlas-weekly-sweep",
    )
    assert "--attempt-deadline=900s" in scheduler
    assert "--max-retry-attempts=0" in scheduler
    assert "--oidc-token-audience=https://atlas-console-test-uc.a.run.app" in scheduler
    assert has_command(recorded, "roles/run.invoker")
    assert has_command(recorded, "scheduler", "jobs", "pause", "atlas-weekly-sweep")
    assert not has_command(recorded, "scheduler", "jobs", "resume")


def test_deploy_only_resumes_scheduler_with_explicit_opt_in(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud

    result = run_script("deploy.sh", [PROJECT, "--resume-scheduler"], env)

    assert result.returncode == 0, result.stdout + result.stderr
    recorded = commands(log_path)
    assert has_command(recorded, "scheduler", "jobs", "pause", "atlas-weekly-sweep")
    assert has_command(recorded, "scheduler", "jobs", "resume", "atlas-weekly-sweep")


def test_cost_guard_is_project_specific_and_updates_an_existing_budget(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud
    env["FAKE_EXISTING_BUDGET"] = (
        f"billingAccounts/{BILLING_ACCOUNT}/budgets/existing-atlas-budget"
    )

    result = run_script("cost_guard.sh", [PROJECT, BILLING_ACCOUNT], env)

    assert result.returncode == 0, result.stdout + result.stderr
    recorded = commands(log_path)
    update = command_with(recorded, "billing", "budgets", "update")
    assert f"ATLAS {PROJECT} gross-spend guard" in update
    assert "--budget-amount=1" in update
    assert f"--filter-projects=projects/{PROJECT}" in update
    assert "--credit-types-treatment=exclude-all-credits" in update


def test_teardown_requires_explicit_project_deletion_confirmation(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud

    result = run_script("teardown.sh", [PROJECT, BILLING_ACCOUNT], env)

    assert result.returncode == 2
    assert "--confirm-delete-project" in result.stdout
    assert not has_command(commands(log_path), "projects", "delete")


def test_confirmed_teardown_deletes_budget_then_the_dedicated_project(
    fake_gcloud: tuple[dict[str, str], Path],
) -> None:
    env, log_path = fake_gcloud
    env["FAKE_EXISTING_BUDGET"] = (
        f"billingAccounts/{BILLING_ACCOUNT}/budgets/atlas-budget"
    )

    result = run_script(
        "teardown.sh",
        [PROJECT, BILLING_ACCOUNT, "--confirm-delete-project"],
        env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    recorded = commands(log_path)
    budget_delete = command_with(recorded, "billing", "budgets", "delete")
    project_delete = command_with(recorded, "projects", "delete")
    assert budget_delete[3] == (
        f"billingAccounts/{BILLING_ACCOUNT}/budgets/atlas-budget"
    )
    assert project_delete[2] == PROJECT
    assert recorded.index(next(e for e in recorded if e["args"] is budget_delete)) < recorded.index(
        next(e for e in recorded if e["args"] is project_delete)
    )
