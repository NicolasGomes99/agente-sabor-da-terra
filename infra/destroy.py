import re

from common import (
    InfraError,
    base_parser,
    main_entry,
    require_commands,
    run_command,
)
from deploy import get_cloud_run_service
from migrate import operation_lock
from provision import (
    describe_json,
    get_active_account,
    get_artifact_repository,
    get_bucket_name,
    get_project,
    get_repository_name,
    get_secret,
    get_sql_instance,
    get_storage_bucket,
    run_json,
)


def get_enabled_services(
    project_id: str,
) -> set[str]:
    services = run_json(
        [
            "gcloud",
            "services",
            "list",
            "--enabled",
            "--project",
            project_id,
            "--format=json",
        ]
    )

    return {
        service["config"]["name"]
        for service in services
        if isinstance(service, dict)
        and (service.get("config") or {}).get("name")
    }


def get_project_billing(
    project_id: str,
) -> dict:
    return run_json(
        [
            "gcloud",
            "billing",
            "projects",
            "describe",
            project_id,
            "--format=json",
        ]
    )


def verify_billing_account(
    config: dict,
) -> None:
    billing = get_project_billing(
        config["project_id"]
    )

    linked_account = str(
        billing.get("billingAccountName", "")
    ).split("/")[-1]

    if (
        linked_account
        and linked_account != config["billing_account_id"]
    ):
        raise InfraError(
            "The project is linked to a different billing account. "
            "Refuse to continue."
        )


def get_project_budgets(
    config: dict,
    project_number: str,
) -> list[dict]:
    project_id = config["project_id"]

    budgets = run_json(
        [
            "gcloud",
            "billing",
            "budgets",
            "list",
            "--billing-account",
            config["billing_account_id"],
            "--format=json",
        ]
    )

    project_keys = {
        f"projects/{project_id}",
        f"projects/{project_number}",
    }

    expected_name = (
        f"Sabor da Terra - {project_id}"
    )

    matching: list[dict] = []

    for budget in budgets:
        if not isinstance(budget, dict):
            continue

        projects = (
            (budget.get("budgetFilter") or {})
            .get("projects") or []
        )

        exclusive = (
            len(projects) == 1
            and projects[0] in project_keys
        )

        if (
            budget.get("displayName") == expected_name
            and exclusive
        ):
            matching.append(budget)

        elif (
            project_keys.intersection(projects)
            or budget.get("displayName") == expected_name
        ):
            print(
                "Warning: budget not owned exclusively "
                "by this infrastructure configuration. "
                "It will be preserved."
            )

    return matching


def get_budget_id(
    budget: dict,
    billing_account_id: str,
) -> str:
    name = budget.get("name", "")

    pattern = (
        rf"billingAccounts/"
        rf"{re.escape(billing_account_id)}"
        rf"/budgets/([a-zA-Z0-9-]+)"
    )

    match = re.fullmatch(
        pattern,
        name,
    )

    if match is None:
        raise InfraError(
            "Unexpected budget resource name."
        )

    return match.group(1)


def inspect_resources(
    config: dict,
    project_number: str,
    services: set[str],
) -> dict:
    project_id = config["project_id"]
    region = config["region"]

    resources = {
        "cloud_run": None,
        "cloud_sql": None,
        "storage": None,
        "artifacts": None,
        "budgets": get_project_budgets(
            config,
            project_number,
        ),
    }

    if "run.googleapis.com" in services:
        resources["cloud_run"] = (
            get_cloud_run_service(config)
        )

    if "sqladmin.googleapis.com" in services:
        resources["cloud_sql"] = get_sql_instance(
            project_id,
            config["database"]["instance_name"],
        )

    if "storage.googleapis.com" in services:
        resources["storage"] = get_storage_bucket(
            project_id,
            get_bucket_name(config),
        )

    if "artifactregistry.googleapis.com" in services:
        resources["artifacts"] = (
            get_artifact_repository(
                project_id,
                region,
                get_repository_name(config),
            )
        )

    bucket = resources["storage"]

    if bucket is not None:
        owner = str(
            bucket.get("projectNumber", "")
        )

        if owner != project_number:
            raise InfraError(
                "The configured bucket belongs to another project. "
                "Refuse to continue."
            )

    return resources


def print_destroy_plan(
    config: dict,
    resources: dict,
) -> None:
    print("\nDestruction plan")
    print(f"Project: {config['project_id']}")
    print(f"Region: {config['region']}")

    names = {
        "cloud_run": (
            config["cloud_run"]["service_name"]
        ),
        "cloud_sql": (
            config["database"]["instance_name"]
        ),
        "storage": get_bucket_name(config),
        "artifacts": get_repository_name(config),
    }

    for key, name in names.items():
        state = (
            "scheduled for deletion"
            if resources[key] is not None
            else "not found or API disabled"
        )

        print(f"- {key}: {name} ({state})")

    print(
        f"- Managed budgets: "
        f"{len(resources['budgets'])}"
    )

    print(
        "- Firebase Hosting, IAM, secrets and other "
        "project resources will be affected by project deletion."
    )

    print(
        "- The billing account and Google account "
        "will not be deleted."
    )

    print(
        "\nWARNING: This operation permanently removes "
        "application resources and may destroy data "
        "that cannot be recovered."
    )


def confirm_destruction(
    project_id: str,
) -> None:
    print(
        "\nStop application usage and automatic triggers "
        "before continuing."
    )

    print(
        "If any database records or documents must be preserved, "
        "cancel now and complete a protected export."
    )

    print(
        "Verify that this project is dedicated exclusively "
        "to the Sabor da Terra application."
    )

    answer = input(
        f"\nType the exact Project ID ({project_id}) "
        "to authorize destruction: "
    ).strip()

    if answer != project_id:
        raise InfraError(
            "Project ID confirmation failed. "
            "Destruction cancelled."
        )


def confirm_external_credentials_revoked(
    config: dict,
    services: set[str],
) -> None:
    project_id = config["project_id"]

    if config["inference"]["mode"] != "developer":
        if "secretmanager.googleapis.com" not in services:
            return

        if get_secret(
            project_id,
            "gemini-api-key",
        ) is None:
            return

    print(
        "\nRevoke the dedicated Gemini Developer API key "
        "in Google AI Studio or Google Cloud Console."
    )

    print(
        "Revoke any external credentials dedicated "
        "to this environment."
    )

    answer = input(
        "Have the dedicated external credentials been "
        "revoked, or were none created? [y/N]: "
    ).strip().lower()

    if answer != "y":
        raise InfraError(
            "External credential revocation was not confirmed."
        )


def pause_automatic_triggers(
    config: dict,
    services: set[str],
) -> None:
    project_id = config["project_id"]
    region = config["region"]

    if "cloudscheduler.googleapis.com" in services:
        jobs = run_json(
            [
                "gcloud",
                "scheduler",
                "jobs",
                "list",
                "--location",
                region,
                "--project",
                project_id,
                "--format=json",
            ]
        )

        for job in jobs:
            if job.get("state") != "ENABLED":
                continue

            name = job["name"]

            prefix = (
                f"projects/{project_id}/locations/"
                f"{region}/jobs/"
            )

            if not name.startswith(prefix):
                raise InfraError(
                    "Unexpected Cloud Scheduler resource name."
                )

            job_id = name.rsplit("/", 1)[-1]

            run_command(
                [
                    "gcloud",
                    "scheduler",
                    "jobs",
                    "pause",
                    job_id,
                    "--location",
                    region,
                    "--project",
                    project_id,
                ]
            )

    if "cloudtasks.googleapis.com" in services:
        queues = run_json(
            [
                "gcloud",
                "tasks",
                "queues",
                "list",
                "--location",
                region,
                "--project",
                project_id,
                "--format=json",
            ]
        )

        for queue in queues:
            if queue.get("state") != "RUNNING":
                continue

            name = queue["name"]

            prefix = (
                f"projects/{project_id}/locations/"
                f"{region}/queues/"
            )

            if not name.startswith(prefix):
                raise InfraError(
                    "Unexpected Cloud Tasks resource name."
                )

            queue_id = name.rsplit("/", 1)[-1]

            run_command(
                [
                    "gcloud",
                    "tasks",
                    "queues",
                    "pause",
                    queue_id,
                    "--location",
                    region,
                    "--project",
                    project_id,
                ]
            )

    print(
        "Automatic triggers in the configured region: paused."
    )


def delete_cloud_run(config: dict) -> None:
    if get_cloud_run_service(config) is None:
        return

    run_command(
        [
            "gcloud",
            "run",
            "services",
            "delete",
            config["cloud_run"]["service_name"],
            "--region",
            config["region"],
            "--project",
            config["project_id"],
            "--quiet",
        ]
    )

    if get_cloud_run_service(config) is not None:
        raise InfraError(
            "Cloud Run service still exists."
        )

    print("Cloud Run service: deleted.")


def delete_cloud_sql(config: dict) -> None:
    project_id = config["project_id"]
    name = config["database"]["instance_name"]

    instance = get_sql_instance(
        project_id,
        name,
    )

    if instance is None:
        return

    run_command(
        [
            "gcloud",
            "sql",
            "instances",
            "patch",
            name,
            "--no-deletion-protection",
            "--no-retain-backups-on-delete",
            "--project",
            project_id,
            "--quiet",
        ]
    )

    run_command(
        [
            "gcloud",
            "sql",
            "instances",
            "delete",
            name,
            "--no-enable-final-backup",
            "--project",
            project_id,
            "--quiet",
        ]
    )

    if get_sql_instance(
        project_id,
        name,
    ) is not None:
        raise InfraError(
            "Cloud SQL instance still exists."
        )

    print("Cloud SQL instance: deleted.")


def delete_storage_bucket(
    config: dict,
    project_number: str,
) -> None:
    project_id = config["project_id"]
    name = get_bucket_name(config)

    bucket = get_storage_bucket(
        project_id,
        name,
    )

    if bucket is None:
        return

    if str(bucket.get("projectNumber")) != project_number:
        raise InfraError(
            "Bucket ownership verification failed."
        )

    soft_delete = (
        bucket.get("softDeletePolicy") or {}
    )

    retention = str(
        soft_delete.get(
            "retentionDurationSeconds",
            0,
        )
    )

    if retention != "0":
        raise InfraError(
            "The bucket has an active soft-delete policy. "
            "Review it manually before destruction."
        )

    run_command(
        [
            "gcloud",
            "storage",
            "rm",
            "--recursive",
            f"gs://{name}/",
            "--project",
            project_id,
            "--quiet",
        ]
    )

    if get_storage_bucket(
        project_id,
        name,
    ) is not None:
        raise InfraError(
            "Cloud Storage bucket still exists."
        )

    print(
        "Cloud Storage bucket and objects: deleted."
    )


def delete_artifact_repository(
    config: dict,
) -> None:
    project_id = config["project_id"]
    region = config["region"]
    name = get_repository_name(config)

    repository = get_artifact_repository(
        project_id,
        region,
        name,
    )

    if repository is None:
        return

    run_command(
        [
            "gcloud",
            "artifacts",
            "repositories",
            "delete",
            name,
            "--location",
            region,
            "--project",
            project_id,
            "--quiet",
        ]
    )

    if get_artifact_repository(
        project_id,
        region,
        name,
    ) is not None:
        raise InfraError(
            "Artifact Registry repository still exists."
        )

    print(
        "Artifact Registry repository and images: deleted."
    )


def verify_residual_resources(
    config: dict,
    services: set[str],
) -> None:
    project_id = config["project_id"]

    if "sqladmin.googleapis.com" in services:
        backups = run_json(
            [
                "gcloud",
                "sql",
                "backups",
                "list",
                "--instance",
                "-",
                "--project",
                project_id,
                "--format=json",
            ]
        )

        if backups:
            raise InfraError(
                "Residual Cloud SQL backups were found. "
                "Review and remove them manually before continuing."
            )

    if "storage.googleapis.com" in services:
        result = run_command(
            [
                "gcloud",
                "storage",
                "ls",
                "--buckets",
                "--soft-deleted",
                "--project",
                project_id,
            ],
            capture_output=True,
        )

        if result.stdout.strip():
            raise InfraError(
                "Soft-deleted buckets were found. "
                "Review their retention and possible costs "
                "before continuing."
            )

    print(
        "Cloud SQL backups and soft-deleted buckets: "
        "no residual resources detected."
    )


def delete_project_budgets(
    config: dict,
    project_number: str,
) -> None:
    billing_account_id = (
        config["billing_account_id"]
    )

    budgets = get_project_budgets(
        config,
        project_number,
    )

    for budget in budgets:
        budget_id = get_budget_id(
            budget,
            billing_account_id,
        )

        run_command(
            [
                "gcloud",
                "billing",
                "budgets",
                "delete",
                budget_id,
                "--billing-account",
                billing_account_id,
                "--quiet",
            ]
        )

    if get_project_budgets(
        config,
        project_number,
    ):
        raise InfraError(
            "Managed project budgets still exist."
        )

    print("Managed project budgets: removed.")


def unlink_project_billing(
    config: dict,
) -> None:
    project_id = config["project_id"]

    verify_billing_account(config)

    billing = get_project_billing(
        project_id
    )

    if billing.get("billingAccountName"):
        run_command(
            [
                "gcloud",
                "billing",
                "projects",
                "unlink",
                project_id,
                "--quiet",
            ]
        )

    billing = get_project_billing(
        project_id
    )

    if (
        billing.get("billingEnabled")
        or billing.get("billingAccountName")
    ):
        raise InfraError(
            "Project billing is still linked."
        )

    print(
        "Billing account: unlinked from project."
    )


def delete_project(project_id: str) -> None:
    run_command(
        [
            "gcloud",
            "projects",
            "delete",
            project_id,
            "--quiet",
        ]
    )

    project = get_project(project_id)

    if project is not None:
        lifecycle = project.get(
            "lifecycleState"
        )

        if lifecycle not in {
            "DELETE_REQUESTED",
            "DELETE_IN_PROGRESS",
            "PENDING_DELETION",
        }:
            raise InfraError(
                "Project deletion could not be verified."
            )

        print(
            f"Project lifecycle: {lifecycle}"
        )

    else:
        print(
            "Project is no longer accessible "
            "through the project lookup."
        )


def destroy(config: dict) -> None:
    require_commands(["gcloud"])

    project_id = config["project_id"]

    with operation_lock():
        account = get_active_account()

        print(
            f"Active gcloud account: {account}"
        )

        project = get_project(
            project_id
        )

        if project is None:
            print(
                f"Project {project_id} was not found. "
                "No resources were modified."
            )

            return

        lifecycle = project.get(
            "lifecycleState"
        )

        if lifecycle in {
            "DELETE_REQUESTED",
            "DELETE_IN_PROGRESS",
            "PENDING_DELETION",
        }:
            print(
                "Project deletion has already been requested."
            )

            print(
                "Review billing and residual resources "
                "in Google Cloud Console."
            )

            return

        if lifecycle != "ACTIVE":
            raise InfraError(
                f"Unexpected project lifecycle: {lifecycle}"
            )

        if not project.get("projectNumber"):
            raise InfraError(
                "Could not determine project number."
            )

        project_number = str(
            project["projectNumber"]
        )

        verify_billing_account(
            config
        )

        services = get_enabled_services(
            project_id
        )

        resources = inspect_resources(
            config,
            project_number,
            services,
        )

        print_destroy_plan(
            config,
            resources,
        )

        confirm_destruction(
            project_id
        )

        confirm_external_credentials_revoked(
            config,
            services,
        )

        pause_automatic_triggers(
            config,
            services,
        )

        if resources["cloud_run"] is not None:
            delete_cloud_run(
                config
            )

        if resources["cloud_sql"] is not None:
            delete_cloud_sql(
                config
            )

        if resources["storage"] is not None:
            delete_storage_bucket(
                config,
                project_number,
            )

        if resources["artifacts"] is not None:
            delete_artifact_repository(
                config
            )

        verify_residual_resources(
            config,
            services,
        )

        unlink_project_billing(
            config
        )

        delete_project_budgets(
            config,
            project_number,
        )

        delete_project(
            project_id
        )

        print(
            "\nDeprovisioning completed."
        )

        print(
            "Project deletion was requested and "
            "billing was unlinked."
        )

        print(
            "Review final billing statements for charges "
            "incurred before deletion."
        )


if __name__ == "__main__":
    main_entry(
        base_parser(
            "Destroy the Sabor da Terra Google Cloud environment"
        ),
        destroy,
    )