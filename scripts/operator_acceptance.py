"""Prepare an isolated synthetic acceptance stack, or recheck a prepared stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/rehearsals/fixtures/operator_acceptance"
DIAGNOSTICS: Path | None = None
FIXTURE_VOLUMES = ["media_data:/app/media", "diagram_jobs:/app/diagram-jobs"]


def isolated_network(info: dict) -> bool:
    return info.get("Internal") is True or info.get("Driver") == "null"


def validate_state(state: dict, directory: Path) -> None:
    if not re.fullmatch(r"tekdocs_acceptance_[0-9a-f]{12}", state.get("project", "")):
        raise ValueError("not a managed acceptance project")
    if not re.fullmatch(r"[0-9a-f]{40}", state.get("source_commit", "")):
        raise ValueError("missing source identity")
    for field in ("port", "mail_port"):
        if type(state.get(field)) is not int or not 1024 <= state[field] <= 65535:
            raise ValueError("invalid local port")
    if state["port"] == state["mail_port"]:
        raise ValueError("ports must be distinct")
    if (
        directory.is_symlink()
        or directory.resolve().parent != (ROOT / "artifacts").resolve()
    ):
        raise ValueError("acceptance state must be a private direct child of artifacts")
    if directory.stat().st_mode & 0o077:
        raise ValueError("acceptance directory must be private (0700)")


def command(args: list[str], *, input: str | None = None) -> str:
    # Preserve CLI discovery and Docker connectivity, never application or
    # Compose interpolation values from an operator's production shell.
    environment = {
        key: os.environ[key]
        for key in (
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        )
        if key in os.environ
    }
    result = subprocess.run(
        args,
        cwd=ROOT,
        input=input,
        capture_output=True,
        text=True,
        timeout=1800,
        env=environment,
    )
    if result.returncode:
        if DIAGNOSTICS is not None and DIAGNOSTICS.parent.is_dir():
            DIAGNOSTICS.write_text(result.stdout + result.stderr)
            DIAGNOSTICS.chmod(0o600)
        # Docker/config/fixture output can contain credentials or authored bytes.
        raise ValueError(
            "acceptance command failed; output withheld to protect fixture credentials"
        )
    return result.stdout


def validate_configuration(state: dict, directory: Path) -> None:
    config = json.loads(
        command(compose(state, directory) + ["config", "--format", "json"])
    )
    if config.get("name") != state["project"]:
        raise ValueError("resolved project is not the disposable project")
    for volume in config.get("volumes", {}).values():
        if volume.get("external") or not volume.get("name", "").startswith(
            state["project"] + "_"
        ):
            raise ValueError("resolved volume is not disposable project storage")
    for name, service in config["services"].items():
        for port in service.get("ports", []):
            if port.get("host_ip") != "127.0.0.1":
                raise ValueError("resolved port is not loopback-only")
        if (
            name not in {"frontend", "mailpit"}
            and service.get("network_mode") != "none"
        ):
            for network in service.get("networks", {}):
                if not config["networks"][network].get("internal"):
                    raise ValueError("resolved backend network permits egress")


def compose(state: dict, directory: Path) -> list[str]:
    validate_state(state, directory)
    return [
        "docker",
        "compose",
        "--project-name",
        state["project"],
        "--env-file",
        str(directory / "local.env"),
        "-f",
        str(ROOT / "compose.yml"),
        "-f",
        str(directory / "compose.json"),
    ]


def fixture(state: dict, directory: Path, name: str) -> None:
    url = f"http://localhost:{state['port']}"
    command(
        compose(state, directory)
        + [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "-e",
            "TEKDOCS_ACCEPTANCE_FIXTURE=isolated-disposable",
            "-e",
            f"TEKDOCS_ACCEPTANCE_URL={url}",
            "-e",
            f"TEKDOCS_ACCEPTANCE_COMMIT={state['source_commit']}",
            "--entrypoint",
            "python",
            "migrate",
            "manage.py",
            "shell",
        ],
        input=(FIXTURES / name).read_text(),
    )
    # The service UID owns fixture files. Copy only the allowlisted outputs to
    # host-private files without printing account credentials or changing UID
    # on the application/repository volumes.
    exported = command(
        compose(state, directory)
        + [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "migrate",
            "-c",
            "import json,pathlib; p=pathlib.Path('/fixture'); "
            "print(json.dumps({n:(p/n).read_text() for n in "
            "['access.txt','manifest.json','verification.json','publication.json'] if (p/n).is_file()}))",
        ]
    )
    for filename, content in json.loads(exported).items():
        if filename not in {
            "access.txt",
            "manifest.json",
            "verification.json",
            "publication.json",
        }:
            raise ValueError("unexpected fixture output")
        target = directory / filename
        if target.is_symlink():
            raise ValueError("symlinked fixture output")
        target.write_text(content)
        target.chmod(0o600)


def doctor(state: dict, directory: Path) -> None:
    base = compose(state, directory)
    readiness = directory / "readiness.json"
    readiness.write_text(
        json.dumps({"ready": False, "checked_at": datetime.now(UTC).isoformat()})
    )
    ids = command(base + ["ps", "-q"]).split()
    if not ids:
        raise ValueError("acceptance stack is down")
    containers = json.loads(command(["docker", "inspect", *ids]))
    services = set()
    for container in containers:
        labels = container["Config"]["Labels"]
        if labels.get("com.docker.compose.project") != state["project"]:
            raise ValueError("foreign container")
        service = labels.get("com.docker.compose.service")
        services.add(service)
        if service in {"worker", "scheduler"}:
            raise ValueError("outbound workers must not run")
        for bindings in container["NetworkSettings"]["Ports"].values():
            if any(b["HostIp"] != "127.0.0.1" for b in bindings or []):
                raise ValueError("acceptance port is not loopback-only")
        if service not in {"frontend", "mailpit"}:
            for network in container["NetworkSettings"]["Networks"]:
                info = json.loads(command(["docker", "network", "inspect", network]))[0]
                if not isolated_network(info):
                    raise ValueError("backend network permits external egress")
    if not {"backend", "frontend", "db", "valkey", "mailpit"} <= services:
        raise ValueError("required acceptance services missing")
    with urlopen(
        f"http://127.0.0.1:{state['port']}/api/v1/health/ready", timeout=10
    ) as response:
        if response.status != 200:
            raise ValueError("acceptance readiness failed")
    fixture(state, directory, "verify.py")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["source_commit"] != state["source_commit"]:
        raise ValueError("fixture source identity mismatch")
    if (
        not (directory / "access.txt").is_file()
        or (directory / "access.txt").stat().st_mode & 0o077
    ):
        raise ValueError("private account file missing or permissions unsafe")
    checked_at = datetime.now(UTC).isoformat()
    guide = [
        "# Prepared operator acceptance",
        "",
        f"Engineering readiness checked {checked_at}. Re-run check before handing this guide to the operator.",
        f"Open http://localhost:{state['port']}",
        f"Source build: `{state['source_commit']}` (not published-image verification).",
        "Credentials: private local `access.txt` beside this guide; never commit or share it.",
        "Sign in as owner@acceptance.invalid and enroll MFA normally. Production credentials do not apply.",
        "",
        "Engineering readiness passed now; operator tests below remain Not run.",
        "",
    ]
    for workspace in manifest["workspaces"]:
        name = workspace["name"]
        guide += [
            f"## {name}",
            "",
            f"- [ ] Open {name}; search Assets for `{name} Laptop 30`, clear search and page through 30 records.",
            f"- [ ] Search Contracts for `{name} Support 30` and Networks for `{name} Network 30`.",
            f"- [ ] Open Documentation → Repository content → `{name} Runbook 01`.",
            "- [ ] Note Loaded Git revision, edit Markdown body, Save to Git, then refresh. The revision changes and the edit remains.",
            "- [ ] Download loaded Markdown and confirm the edit. Check Files for this document lists a retained attachment.",
            "",
        ]
    guide += [
        "## Restricted access",
        "",
        "Use a private window and reader-a@acceptance.invalid. A is readable; B must not be searchable or readable through a copied owner URL.",
        "",
        "## Retained publication",
        "",
        "Use client-a@acceptance.invalid in a separate window. Open New publications, Acceptance A Runbook 01; download its PDF and both primary-file versions. Later live edits must not alter this retained snapshot.",
        "",
        "Report Pass, Fail or Blocked with the step and expected/observed result. Do not include secrets.",
        "Imported NetBox, controlled outage, real-device and screen-reader sessions require separate preparation; no live provider should be configured.",
    ]
    (directory / "walkthrough.md").write_text("\n".join(guide) + "\n")
    readiness.write_text(
        json.dumps(
            {
                "ready": True,
                "checked_at": checked_at,
                "source_commit": state["source_commit"],
            }
        )
    )


def prepare(directory: Path, port: int, mail_port: int) -> dict:
    if directory.exists():
        raise ValueError(
            "destination exists; use check, never reseed an existing installation"
        )
    if directory.parent.resolve() != (ROOT / "artifacts").resolve():
        raise ValueError("choose a direct child of artifacts")
    dirty = command(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "backend",
            "frontend",
            "renderer",
        ]
    )
    if dirty.strip():
        raise ValueError(
            "runtime source is dirty; commit it before claiming a source build identity"
        )
    directory.mkdir(mode=0o700)
    # This child is individually mounted into the service. The private parent
    # protects host custody while allowing the unrelated container UID to write.
    (directory / "data").mkdir()
    (directory / "data").chmod(0o777)
    state = {
        "project": "tekdocs_acceptance_" + secrets.token_hex(6),
        "port": port,
        "mail_port": mail_port,
        "source_commit": command(["git", "rev-parse", "HEAD"]).strip(),
    }
    validate_state(state, directory)
    command([str(ROOT / "scripts/bootstrap-env.sh"), str(directory / "local.env")])
    url = f"http://localhost:{port}"
    env = {
        "TEKDOCS_PUBLIC_URL": url,
        "DJANGO_CSRF_TRUSTED_ORIGINS": url,
        "TEKDOCS_ALLOW_INSECURE_PUBLIC_URL": "true",
        "TEKDOCS_ALLOW_DEVELOPMENT_IMAGE": "true",
        "EMAIL_HOST": "mailpit",
        "EMAIL_PORT": "1025",
    }
    overlay = {
        "services": {
            "migrate": {
                "environment": env,
                "volumes": [f"{directory / 'data'}:/fixture", *FIXTURE_VOLUMES],
            },
            "backend": {"environment": env},
            "frontend": {"networks": ["internal", "acceptance_ui"]},
            "mailpit": {"networks": ["internal", "acceptance_ui"]},
        },
        "networks": {"internal": {"internal": True}, "acceptance_ui": {}},
    }
    # Frontend's base variable includes its host binding; Mailpit binds loopback itself.
    with (directory / "local.env").open("a") as stream:
        stream.write(
            f"\nCOMPOSE_PROJECT_NAME={state['project']}\nTEKDOCS_PORT=127.0.0.1:{port}\nMAILPIT_UI_PORT={mail_port}\n"
        )
    (directory / "compose.json").write_text(json.dumps(overlay))
    (directory / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    validate_configuration(state, directory)
    command(
        compose(state, directory)
        + ["up", "-d", "--build", "--wait", "backend", "frontend", "mailpit"]
    )
    for name in ("seed.py", "accounts.py", "network_template.py", "publication.py"):
        fixture(state, directory, name)
    doctor(state, directory)
    return state


def main() -> int:
    global DIAGNOSTICS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "check"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=3298)
    parser.add_argument("--mail-port", type=int, default=8098)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        directory = args.directory.absolute()
        if directory.parent.resolve() == (ROOT / "artifacts").resolve():
            DIAGNOSTICS = directory / "private-command.log"
        if args.action == "prepare":
            prepare(directory, args.port, args.mail_port)
        else:
            doctor(json.loads((directory / "state.json").read_text()), directory)
        print(f"Prepared walkthrough: {directory / 'walkthrough.md'}")
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print(
            "Acceptance is NOT ready. Existing containers/data were retained; no walkthrough pass is claimed."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
