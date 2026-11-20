import asyncio
import shutil
import socket
import subprocess
import tempfile
import time
from typing import TextIO, cast

import asyncpg

from common import (
    InfraError,
    redact_text,
    register_secret,
    require_commands,
)


PROXY_START_TIMEOUT_SECONDS = 60


def connection_name(
    project_id: str,
    region: str,
    instance_name: str,
) -> str:
    return f"{project_id}:{region}:{instance_name}"


def find_free_tcp_port() -> int:
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:
        sock.bind(("127.0.0.1", 0))

        return int(sock.getsockname()[1])


def _read_stderr(
    stream: TextIO | None,
) -> str:
    if stream is None:
        return ""

    try:
        stream.flush()
        stream.seek(0)

        return redact_text(
            stream.read().strip()
        )

    except (OSError, ValueError):
        return ""


class CloudSqlProxy:
    """Manage a Cloud SQL Auth Proxy bound to loopback."""

    def __init__(
        self,
        project_id: str,
        connection_name: str,
        *,
        proxy_path: str = "cloud-sql-proxy",
        port: int | None = None,
        timeout_seconds: int = PROXY_START_TIMEOUT_SECONDS,
    ) -> None:
        self.project_id = project_id
        self.connection_name = connection_name
        self.proxy_path = proxy_path
        self.requested_port = port
        self.timeout_seconds = timeout_seconds

        self.port: int | None = None

        self._process: subprocess.Popen[str] | None = None
        self._stderr: TextIO | None = None

    @property
    def host(self) -> str:
        return "127.0.0.1"

    def __enter__(self) -> "CloudSqlProxy":
        self.start()

        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        self.stop()

        return False

    def _command(self) -> list[str]:
        if self.port is None:
            raise InfraError(
                "Cloud SQL Auth Proxy port is not configured."
            )

        executable = (
            shutil.which(self.proxy_path)
            or self.proxy_path
        )

        return [
            executable,
            f"--address={self.host}",
            f"--port={self.port}",
            f"--quota-project={self.project_id}",
            self.connection_name,
        ]

    def _validate_port(self) -> None:
        if (
            self.port is None
            or not 1 <= self.port <= 65535
        ):
            raise InfraError(
                "Cloud SQL Auth Proxy port must be "
                "between 1 and 65535."
            )

        if self.requested_port is None:
            return

        try:
            with socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM,
            ) as sock:
                sock.bind(
                    (self.host, self.port)
                )

        except OSError:
            raise InfraError(
                f"Port {self.port} is unavailable."
            ) from None

    def start(self) -> None:
        if self._process is not None:
            raise InfraError(
                "Cloud SQL Auth Proxy is already started."
            )

        require_commands(
            [self.proxy_path]
        )

        if self.timeout_seconds <= 0:
            raise InfraError(
                "Proxy startup timeout must be positive."
            )

        self.port = (
            self.requested_port
            if self.requested_port is not None
            else find_free_tcp_port()
        )

        self._validate_port()

        self._stderr = cast(
            TextIO,
            tempfile.TemporaryFile(
                mode="w+",
                encoding="utf-8",
                errors="replace",
            ),
        )

        try:
            self._process = subprocess.Popen(
                self._command(),
                stdout=subprocess.DEVNULL,
                stderr=self._stderr,
                text=True,
                shell=False,
            )

            self._wait_until_ready()

        except OSError as error:
            self.stop()

            raise InfraError(
                "Could not start Cloud SQL Auth Proxy: "
                f"{redact_text(str(error))}"
            ) from None

        except BaseException:
            self.stop()

            raise

        print(
            f"Cloud SQL Auth Proxy: listening on "
            f"{self.host}:{self.port}"
        )

    def _wait_until_ready(self) -> None:
        if self.port is None:
            raise InfraError(
                "Cloud SQL Auth Proxy port is not configured."
            )

        deadline = (
            time.monotonic()
            + self.timeout_seconds
        )

        while time.monotonic() < deadline:
            process = self._process

            if process is None:
                raise InfraError(
                    "Cloud SQL Auth Proxy process is unavailable."
                )

            exit_code = process.poll()

            if exit_code is not None:
                detail = _read_stderr(
                    self._stderr
                )

                message = (
                    "Cloud SQL Auth Proxy exited before "
                    "accepting connections "
                    f"(exit code {exit_code})."
                )

                if detail:
                    message += f"\n{detail[-4000:]}"

                raise InfraError(message)

            try:
                with socket.create_connection(
                    (self.host, self.port),
                    timeout=1,
                ):
                    if process.poll() is None:
                        return

            except OSError:
                pass

            time.sleep(0.5)

        detail = _read_stderr(
            self._stderr
        )

        message = (
            "Cloud SQL Auth Proxy did not accept "
            "connections before the timeout."
        )

        if detail:
            message += f"\n{detail[-4000:]}"

        raise InfraError(message)

    def stop(self) -> None:
        process = self._process

        try:
            if (
                process is not None
                and process.poll() is None
            ):
                process.terminate()

                try:
                    process.wait(timeout=10)

                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        finally:
            self._process = None

            self._close_stderr()

    def _close_stderr(self) -> None:
        if self._stderr is None:
            return

        try:
            self._stderr.close()

        finally:
            self._stderr = None


async def run_postgres_sql(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    sql: str,
) -> None:
    if host != "127.0.0.1":
        raise InfraError(
            "PostgreSQL connections must use "
            "the local Cloud SQL Auth Proxy."
        )

    register_secret(password)

    try:
        connection = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            ssl=False,
            timeout=15,
            command_timeout=60,
            server_settings={
                "application_name": (
                    "sabor-da-terra-infra"
                ),
            },
        )

        try:
            async with connection.transaction():
                await connection.execute(sql)

        finally:
            await connection.close(timeout=10)

    except (
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
        OSError,
        TimeoutError,
    ) as error:
        message = redact_text(
            str(error)
        )

        raise InfraError(
            "Cloud SQL configuration failed "
            f"({type(error).__name__}): {message}"
        ) from None


def run_sql_with_proxy(
    project_id: str,
    connection_name: str,
    database_name: str,
    user: str,
    password: str,
    sql: str,
    *,
    proxy_path: str = "cloud-sql-proxy",
) -> None:
    with CloudSqlProxy(
        project_id,
        connection_name,
        proxy_path=proxy_path,
    ) as proxy:
        if proxy.port is None:
            raise InfraError(
                "Cloud SQL Auth Proxy has no assigned port."
            )

        asyncio.run(
            run_postgres_sql(
                host=proxy.host,
                port=proxy.port,
                user=user,
                password=password,
                database=database_name,
                sql=sql,
            )
        )

    print(
        "PostgreSQL configuration completed successfully."
    )