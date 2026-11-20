import json
import re
from typing import Any, Callable

from common import (
    InfraError,
    require_commands,
    run_command,
)


def run_firebase_json(
    arguments: list[str],
) -> Any:
    command = [
        "firebase",
        *arguments,
        "--non-interactive",
        "--json",
    ]

    response = run_command(
        command,
        capture_output=True,
    )

    try:
        payload = json.loads(response.stdout)
    except json.JSONDecodeError:
        raise InfraError(
            "Firebase CLI returned invalid JSON."
        ) from None

    if not isinstance(payload, dict):
        raise InfraError(
            "Unexpected Firebase CLI response."
        )

    if payload.get("status") != "success":
        raise InfraError(
            "Firebase CLI did not report success."
        )

    if "result" not in payload:
        raise InfraError(
            "Firebase CLI response has no result."
        )

    return payload["result"]


def list_firebase_projects() -> list[dict]:
    projects = run_firebase_json(
        ["projects:list"]
    )

    if not isinstance(projects, list):
        raise InfraError(
            "Unexpected Firebase projects response."
        )

    if not all(
        isinstance(project, dict)
        for project in projects
    ):
        raise InfraError(
            "Invalid Firebase project metadata."
        )

    return projects


def get_firebase_project(
    project_id: str,
) -> dict | None:
    projects = list_firebase_projects()

    for project in projects:
        if project.get("projectId") == project_id:
            return project

    return None


def ensure_firebase_project(
    project_id: str,
    *,
    confirm: Callable[[str], None],
) -> None:
    project = get_firebase_project(project_id)

    if project is not None:
        print(
            f"Firebase project {project_id}: already associated."
        )
        return

    confirm(
        f"Associate Firebase with Google Cloud project "
        f"{project_id}?"
    )

    run_firebase_json(
        [
            "projects:addfirebase",
            project_id,
        ]
    )

    if get_firebase_project(project_id) is None:
        raise InfraError(
            "Could not verify Firebase project association."
        )

    print(
        f"Firebase project {project_id}: associated."
    )


def list_hosting_sites(
    project_id: str,
) -> list[dict]:
    result = run_firebase_json(
        [
            "hosting:sites:list",
            "--project",
            project_id,
        ]
    )

    if not isinstance(result, dict):
        raise InfraError(
            "Unexpected Firebase Hosting sites response."
        )

    sites = result.get("sites")

    if not isinstance(sites, list):
        raise InfraError(
            "Firebase Hosting response has no sites list."
        )

    if not all(
        isinstance(site, dict)
        for site in sites
    ):
        raise InfraError(
            "Invalid Firebase Hosting site metadata."
        )

    return sites


def get_default_hosting_site(
    project_id: str,
) -> dict | None:
    sites = list_hosting_sites(project_id)

    default_sites = [
        site
        for site in sites
        if site.get("type") == "DEFAULT_SITE"
    ]

    if len(default_sites) > 1:
        raise InfraError(
            "Multiple default Firebase Hosting sites found."
        )

    if default_sites:
        return default_sites[0]

    if sites:
        raise InfraError(
            "Firebase Hosting sites exist, but no default "
            "site could be identified."
        )

    return None


def get_hosting_site_id(site: dict) -> str:
    name = site.get("name")

    if not isinstance(name, str):
        raise InfraError(
            "Firebase Hosting site has no resource name."
        )

    match = re.fullmatch(
        r"projects/[^/]+/sites/([a-z0-9-]+)",
        name,
    )

    if match is None:
        raise InfraError(
            "Invalid Firebase Hosting resource name."
        )

    site_id = match.group(1)

    if (
        len(site_id) > 63
        or site_id.startswith("-")
        or site_id.endswith("-")
    ):
        raise InfraError(
            "Invalid Firebase Hosting site ID."
        )

    return site_id


def get_hosting_origins(site: dict) -> list[str]:
    site_id = get_hosting_site_id(site)

    origins = [
        f"https://{site_id}.web.app",
        f"https://{site_id}.firebaseapp.com",
    ]

    default_url = site.get("defaultUrl")

    if (
        not isinstance(default_url, str)
        or default_url.rstrip("/") not in origins
    ):
        raise InfraError(
            "Unexpected Firebase Hosting default URL."
        )

    return origins


def require_default_hosting_site(
    project_id: str,
) -> dict:
    site = get_default_hosting_site(project_id)

    if site is None:
        raise InfraError(
            "Default Firebase Hosting site not found. "
            "Run the provisioning script first."
        )

    get_hosting_origins(site)

    return site


def ensure_default_hosting_site(
    project_id: str,
    *,
    confirm: Callable[[str], None],
) -> dict:
    site = get_default_hosting_site(project_id)

    if site is None:
        confirm(
            f"Create the default Firebase Hosting site "
            f"with ID {project_id}?"
        )

        run_firebase_json(
            [
                "hosting:sites:create",
                project_id,
                "--project",
                project_id,
            ]
        )

        site = require_default_hosting_site(
            project_id
        )

    site_id = get_hosting_site_id(site)
    origins = get_hosting_origins(site)

    print(
        f"Firebase Hosting site {site_id}: configured."
    )

    for origin in origins:
        print(f"Hosting origin: {origin}")

    return site


def ensure_hosting(
    project_id: str,
    *,
    confirm: Callable[[str], None],
) -> dict:
    require_commands(["firebase"])

    ensure_firebase_project(
        project_id,
        confirm=confirm,
    )

    return ensure_default_hosting_site(
        project_id,
        confirm=confirm,
    )


def publish_hosting(project_id: str) -> list[str]:
    require_commands(["firebase"])

    site = require_default_hosting_site(
        project_id
    )

    run_command(
        [
            "firebase",
            "deploy",
            "--only",
            "hosting",
            "--project",
            project_id,
            "--non-interactive",
        ]
    )

    origins = get_hosting_origins(site)

    print("Firebase Hosting: deployment completed.")

    for origin in origins:
        print(f"Frontend URL: {origin}")

    return origins