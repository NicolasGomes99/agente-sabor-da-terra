import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from cloudsql import connection_name
from common import (
    REPOSITORY_ROOT,
    InfraError,
    base_parser,
    main_entry,
    require_commands,
    require_git_clean,
    run_command,
)
from hosting import (
    get_hosting_origins,
    publish_hosting,
    require_default_hosting_site,
)
from migrate import (
    get_migration_head,
    migrate,
    operation_lock,
)
from provision import (
    SERVICE_ACCOUNTS,
    confirm,
    describe_json,
    get_active_account,
    get_artifact_repository,
    get_bucket_name,
    get_project,
    get_repository_name,
    get_secret_version,
    get_sql_instance,
    get_storage_bucket,
    validate_artifact_repository,
    validate_sql_instance,
    validate_storage_bucket,
)


BACKEND_DIR = REPOSITORY_ROOT / "backend"
FRONTEND_DIR = REPOSITORY_ROOT / "frontend"

DIGEST_PATTERN = re.compile(
    r"sha256:[a-f0-9]{64}"
)

COMMIT_PATTERN = re.compile(
    r"[a-f0-9]{40}"
)


def get_git_commit() -> str:
    result = run_command(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
    )

    commit = result.stdout.strip()

    if not COMMIT_PATTERN.fullmatch(commit):
        raise InfraError(
            "Could not determine the Git commit hash."
        )

    return commit


def verify_git_commit(expected_commit: str) -> None:
    require_git_clean()

    current_commit = get_git_commit()

    if current_commit != expected_commit:
        raise InfraError(
            "Git commit changed during deployment."
        )


def get_registry_host(config: dict) -> str:
    return (
        f"{config['region']}-docker.pkg.dev"
    )


def get_image_name(config: dict) -> str:
    return (
        f"{get_registry_host(config)}/"
        f"{config['project_id']}/"
        f"{get_repository_name(config)}/backend"
    )


def get_image_digest(
    project_id: str,
    image_reference: str,
) -> str | None:
    image = describe_json(
        [
            "gcloud",
            "artifacts",
            "docker",
            "images",
            "describe",
            image_reference,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Artifact Registry image {image_reference} lookup",
    )

    if image is None:
        return None

    summary = image.get("image_summary") or {}
    digest = summary.get("digest")

    if (
        not isinstance(digest, str)
        or not DIGEST_PATTERN.fullmatch(digest)
    ):
        raise InfraError(
            "Artifact Registry returned an invalid image digest."
        )

    return digest


def ensure_docker_available() -> None:
    run_command(
        [
            "docker",
            "info",
            "--format",
            "{{.ServerVersion}}",
        ],
        capture_output=True,
    )


def configure_docker_auth(config: dict) -> None:
    registry_host = get_registry_host(config)

    run_command(
        [
            "gcloud",
            "auth",
            "configure-docker",
            registry_host,
            "--quiet",
        ]
    )


def build_and_push_image(
    config: dict,
    commit: str,
) -> str:
    project_id = config["project_id"]
    image_name = get_image_name(config)

    tagged_image = (
        f"{image_name}:{commit}"
    )

    existing_digest = get_image_digest(
        project_id,
        tagged_image,
    )

    if existing_digest is not None:
        print(
            "An image already exists for this Git commit. "
            "Reusing it without overwriting its tag."
        )

        return (
            f"{image_name}@{existing_digest}"
        )

    verify_git_commit(commit)

    configure_docker_auth(config)

    print(f"Building backend image: {tagged_image}")

    run_command(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--file",
            str(BACKEND_DIR / "dockerfile"),
            "--label",
            f"org.opencontainers.image.revision={commit}",
            "--tag",
            tagged_image,
            str(BACKEND_DIR),
        ]
    )

    verify_git_commit(commit)

    existing_digest = get_image_digest(
        project_id,
        tagged_image,
    )

    if existing_digest is not None:
        raise InfraError(
            "The image tag appeared during the build. "
            "Refuse to overwrite it."
        )

    print(
        f"Pushing backend image: {tagged_image}"
    )

    run_command(
        [
            "docker",
            "push",
            tagged_image,
        ]
    )

    digest = get_image_digest(
        project_id,
        tagged_image,
    )

    if digest is None:
        raise InfraError(
            "Image was not found in Artifact Registry "
            "after pushing."
        )

    image_reference = (
        f"{image_name}@{digest}"
    )

    print(
        f"Published image: {image_reference}"
    )

    return image_reference


def verify_provisioned_resources(
    config: dict,
) -> None:
    project_id = config["project_id"]
    region = config["region"]

    project = get_project(project_id)

    if project is None:
        raise InfraError(
            "Google Cloud project not found. "
            "Run provision.py first."
        )

    if project.get("lifecycleState") != "ACTIVE":
        raise InfraError(
            "Google Cloud project is not active."
        )

    project_number = project.get(
        "projectNumber"
    )

    if not project_number:
        raise InfraError(
            "Could not determine project number."
        )

    repository = get_artifact_repository(
        project_id,
        region,
        get_repository_name(config),
    )

    if repository is None:
        raise InfraError(
            "Artifact Registry repository not found."
        )

    validate_artifact_repository(
        repository
    )

    instance = get_sql_instance(
        project_id,
        config["database"]["instance_name"],
    )

    if instance is None:
        raise InfraError(
            "Cloud SQL instance not found."
        )

    validate_sql_instance(
        instance,
        config,
    )

    if instance.get("state") != "RUNNABLE":
        raise InfraError(
            "Cloud SQL instance is not ready."
        )

    bucket = get_storage_bucket(
        project_id,
        get_bucket_name(config),
    )

    if bucket is None:
        raise InfraError(
            "Cloud Storage bucket not found."
        )

    validate_storage_bucket(
        bucket,
        str(project_number),
        region,
    )

    print(
        "Provisioned cloud resources: verified."
    )


def build_environment_variables(
    config: dict,
    origins: list[str],
) -> dict[str, str]:
    inference = config["inference"]

    variables = {
        "DOCUMENT_STORAGE_BACKEND": "gcs",
        "DOCUMENT_STORAGE_BUCKET": (
            get_bucket_name(config)
        ),
        "CORS_ALLOWED_ORIGINS": (
            ",".join(origins)
        ),
        "GEMINI_AGENT_MODEL": (
            inference["model"]
        ),
        "GOOGLE_GENAI_USE_ENTERPRISE": "FALSE",
    }

    if inference["mode"] == "vertex":
        variables.update(
            {
                "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
                "GOOGLE_CLOUD_PROJECT": (
                    config["project_id"]
                ),
                "GOOGLE_CLOUD_LOCATION": (
                    inference.get("location") or "global"
                ),
            }
        )

    elif inference["mode"] == "developer":
        variables[
            "GOOGLE_GENAI_USE_VERTEXAI"
        ] = "FALSE"

    else:
        raise InfraError(
            "Unsupported inference mode."
        )

    return variables


def build_secret_references(
    config: dict,
) -> dict[str, str]:
    project_id = config["project_id"]

    names = {
        "DATABASE_URL": "database-url",
        "JWT_SECRET_KEY": "jwt-secret-key",
    }

    if config["inference"]["mode"] == "developer":
        names[
            "GEMINI_API_KEY"
        ] = "gemini-api-key"

    references: dict[str, str] = {}

    for variable, secret_name in names.items():
        version = get_secret_version(
            project_id,
            secret_name,
        )

        references[variable] = (
            f"{secret_name}:{version}"
        )

    return references


def encode_gcloud_mapping(
    values: dict[str, str],
) -> str:
    delimiter = "@"

    for key, value in values.items():
        if not re.fullmatch(
            r"[A-Z_][A-Z0-9_]*",
            key,
        ):
            raise InfraError(
                "Invalid environment variable name."
            )

        if (
            delimiter in value
            or "\n" in value
            or "\r" in value
        ):
            raise InfraError(
                f"Invalid value for environment variable {key}."
            )

    entries = [
        f"{key}={value}"
        for key, value in values.items()
    ]

    return (
        f"^{delimiter}^"
        + delimiter.join(entries)
    )


def build_cloud_run_command(
    config: dict,
    image_reference: str,
    variables: dict[str, str],
    secret_references: dict[str, str],
) -> list[str]:
    project_id = config["project_id"]
    region = config["region"]
    cloud_run = config["cloud_run"]

    if cloud_run["billing"] != "request-based":
        raise InfraError(
            "Only request-based Cloud Run billing is supported."
        )

    instance_connection = connection_name(
        project_id,
        region,
        config["database"]["instance_name"],
    )

    service_account = (
        f"{SERVICE_ACCOUNTS['api'][0]}"
        f"@{project_id}.iam.gserviceaccount.com"
    )

    return [
        "gcloud",
        "run",
        "deploy",
        cloud_run["service_name"],
        "--image",
        image_reference,
        "--project",
        project_id,
        "--region",
        region,
        "--platform=managed",
        "--execution-environment=gen1",
        "--ingress=all",
        "--no-invoker-iam-check",
        "--service-account",
        service_account,
        "--port=8080",
        f"--cpu={cloud_run['cpu']}",
        f"--memory={cloud_run['memory']}",
        f"--min={cloud_run['min_instances']}",
        f"--max={cloud_run['max_instances']}",
        f"--concurrency={cloud_run['concurrency']}",
        f"--timeout={cloud_run['timeout_seconds']}s",
        "--cpu-throttling",
        "--set-cloudsql-instances",
        instance_connection,
        "--set-env-vars",
        encode_gcloud_mapping(variables),
        "--set-secrets",
        encode_gcloud_mapping(secret_references),
        "--quiet",
    ]


def get_cloud_run_service(
    config: dict,
) -> dict | None:
    service_name = (
        config["cloud_run"]["service_name"]
    )

    return describe_json(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            service_name,
            "--region",
            config["region"],
            "--project",
            config["project_id"],
            "--format=json",
        ],
        f"Cloud Run service {service_name} lookup",
    )


def verify_cloud_run_service(
    config: dict,
    image_reference: str,
) -> str:
    service = get_cloud_run_service(
        config
    )

    if service is None:
        raise InfraError(
            "Cloud Run service not found after deployment."
        )

    status = service.get("status") or {}

    ready = next(
        (
            condition
            for condition in status.get("conditions", [])
            if condition.get("type") == "Ready"
        ),
        None,
    )

    if ready is None or ready.get("status") != "True":
        raise InfraError(
            "Cloud Run service is not ready."
        )

    created_revision = status.get(
        "latestCreatedRevisionName"
    )

    ready_revision = status.get(
        "latestReadyRevisionName"
    )

    if (
        not ready_revision
        or ready_revision != created_revision
    ):
        raise InfraError(
            "The latest Cloud Run revision is not ready."
        )

    template = (
        (service.get("spec") or {})
        .get("template") or {}
    )

    containers = (
        (template.get("spec") or {})
        .get("containers") or []
    )

    if len(containers) != 1:
        raise InfraError(
            "Unexpected Cloud Run container configuration."
        )

    if containers[0].get("image") != image_reference:
        raise InfraError(
            "Cloud Run image does not match "
            "the published image digest."
        )

    url = status.get("url")

    if not isinstance(url, str):
        raise InfraError(
            "Cloud Run service has no URL."
        )

    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".run.app")
    ):
        raise InfraError(
            "Invalid Cloud Run service URL."
        )

    print(
        f"Cloud Run revision: {ready_revision}"
    )

    print(f"Backend URL: {url}")

    return url.rstrip("/")


def deploy_backend(
    config: dict,
    image_reference: str,
    origins: list[str],
) -> str:
    variables = build_environment_variables(
        config,
        origins,
    )

    references = build_secret_references(
        config
    )

    command = build_cloud_run_command(
        config,
        image_reference,
        variables,
        references,
    )

    print("Deploying backend to Cloud Run...")

    run_command(command)

    url = verify_cloud_run_service(
        config,
        image_reference,
    )

    run_command(
        [
            "gcloud",
            "run",
            "services",
            "update-traffic",
            config["cloud_run"]["service_name"],
            "--to-latest",
            "--region",
            config["region"],
            "--project",
            config["project_id"],
            "--quiet",
        ]
    )

    return url


def verify_backend_http(
    api_url: str,
    origins: list[str],
) -> None:
    request = Request(
        f"{api_url}/openapi.json",
        headers={
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(
            request,
            timeout=90,
        ) as response:
            schema = json.load(response)

            if response.status != 200:
                raise InfraError(
                    "Backend did not return HTTP 200."
                )

    except (
        URLError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        raise InfraError(
            "Backend OpenAPI verification failed."
        ) from None

    paths = schema.get("paths") or {}

    if "/auth/login" not in paths:
        raise InfraError(
            "Published backend does not expose "
            "the expected login endpoint."
        )

    for origin in origins:
        preflight = Request(
            f"{api_url}/auth/login",
            method="OPTIONS",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": (
                    "content-type"
                ),
            },
        )

        try:
            with urlopen(
                preflight,
                timeout=30,
            ) as response:
                allowed_origin = response.headers.get(
                    "Access-Control-Allow-Origin"
                )

                if allowed_origin != origin:
                    raise InfraError(
                        f"Unexpected CORS policy for {origin}."
                    )

        except (
            URLError,
            TimeoutError,
            OSError,
        ):
            raise InfraError(
                f"Backend CORS verification failed for {origin}."
            ) from None

    verify_protected_endpoint(
        api_url,
        paths,
    )

    print(
        "Backend HTTP, OpenAPI, CORS and "
        "authentication boundary: verified."
    )


def verify_protected_endpoint(
    api_url: str,
    paths: dict,
) -> None:
    protected_path = None

    for path, methods in paths.items():
        if "{" in path:
            continue

        operation = methods.get("get")

        if (
            isinstance(operation, dict)
            and operation.get("security")
        ):
            protected_path = path
            break

    if protected_path is None:
        raise InfraError(
            "Could not identify a protected GET endpoint "
            "in the published OpenAPI schema."
        )

    request = Request(
        f"{api_url}{protected_path}"
    )

    try:
        with urlopen(
            request,
            timeout=30,
        ):
            raise InfraError(
                "A protected endpoint accepted a request "
                "without authentication."
            )

    except HTTPError as error:
        try:
            if error.code != 401:
                raise InfraError(
                    "Unexpected unauthenticated response: "
                    f"HTTP {error.code}."
                ) from None
        finally:
            error.close()

    except (
        URLError,
        TimeoutError,
        OSError,
    ):
        raise InfraError(
            "Protected endpoint verification failed."
        ) from None


def build_frontend(api_url: str) -> None:
    print("Installing frontend dependencies...")

    run_command(
        [
            "npm",
            "ci",
        ],
        cwd=FRONTEND_DIR,
    )

    print("Building frontend...")

    run_command(
        [
            "npm",
            "run",
            "build",
        ],
        cwd=FRONTEND_DIR,
        env={
            "VITE_API_URL": api_url,
        },
    )

    index = (
        FRONTEND_DIR
        / "dist"
        / "index.html"
    )

    if not index.is_file():
        raise InfraError(
            "Frontend build did not produce dist/index.html."
        )


def verify_frontend_http(
    origins: list[str],
) -> None:
    for origin in origins:
        request = Request(origin)

        try:
            with urlopen(
                request,
                timeout=30,
            ) as response:
                content = response.read().lower()

                if (
                    response.status != 200
                    or b"<html" not in content
                ):
                    raise InfraError(
                        f"Invalid frontend response from {origin}."
                    )

        except (
            URLError,
            TimeoutError,
            OSError,
        ):
            raise InfraError(
                f"Frontend verification failed for {origin}."
            ) from None

        print(
            f"Frontend HTTP: verified at {origin}"
        )


def deploy(config: dict) -> None:
    require_commands(
        [
            "gcloud",
            "firebase",
            "docker",
            "npm",
            "uv",
            "git",
            "node",
        ]
    )

    with operation_lock():
        require_git_clean()

        commit = get_git_commit()

        head = get_migration_head()

        account = get_active_account()

        ensure_docker_available()

        verify_provisioned_resources(
            config
        )

        site = require_default_hosting_site(
            config["project_id"]
        )

        origins = get_hosting_origins(
            site
        )

        # Check secret availability before building or
        # modifying application resources.
        build_secret_references(config)

        get_secret_version(
            config["project_id"],
            "database-migrator-password",
        )

        print("\nDeployment configuration")
        print(f"Account: {account}")
        print(f"Project: {config['project_id']}")
        print(f"Region: {config['region']}")
        print(f"Commit: {commit}")
        print(f"Alembic head: {head}")
        print(f"Inference: {config['inference']['mode']}")
        print(
            f"Model: {config['inference']['model']}"
        )

        confirm(
            "Deploy this Git commit? Confirm that tests passed, "
            "public endpoints were reviewed and database "
            "migrations are safe. Cloud resources may "
            "generate charges."
        )

        if get_cloud_run_service(config) is not None:
            confirm(
                "An existing backend will be updated. "
                "Confirm that incompatible migrations have "
                "been reviewed and application usage and "
                "automatic triggers are stopped if necessary."
            )

        image_reference = build_and_push_image(
            config,
            commit,
        )

        verify_git_commit(commit)

        migrate(
            config,
            acquire_lock=False,
        )

        verify_git_commit(commit)

        api_url = deploy_backend(
            config,
            image_reference,
            origins,
        )

        verify_backend_http(
            api_url,
            origins,
        )

        verify_git_commit(commit)

        build_frontend(api_url)

        verify_git_commit(commit)

        published_origins = publish_hosting(
            config["project_id"]
        )

        if set(published_origins) != set(origins):
            raise InfraError(
                "Firebase Hosting origins changed during deployment."
            )

        verify_frontend_http(
            published_origins
        )

        print("\nDeployment completed successfully.")
        print(f"Git commit: {commit}")
        print(f"Database revision: {head}")
        print(f"Image: {image_reference}")
        print(f"Backend: {api_url}")

        for origin in published_origins:
            print(f"Frontend: {origin}")

        print(
            "Next step: authenticated functional smoke tests "
            "for database, documents and agents."
        )


if __name__ == "__main__":
    main_entry(
        base_parser(
            "Build and deploy the Sabor da Terra application"
        ),
        deploy,
    )