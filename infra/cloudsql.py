import socket
import subprocess
import tempfile
import time
from typing import TextIO

from common import (
    InfraError,
    command_failure,
    redact_text,
    register_secret,
    require_commands,
    run_command,
)


PROXY_START_TIMEOUT_SECONDS = 60


def find_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_stderr(stream: TextIO | None) -> str:
    if stream is None:
        return ""
    try:
        stream.flush()
        stream.seek(0)
        return redact_text(stream.read().strip())
    except (OSError, ValueError):
        return ""


class CloudSqlProxy:
    """Manage a local Cloud SQL Auth Proxy process bound to loopback."""

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

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.stop()
        return False

    def _command(self) -> list[str]:
        assert self.port is not None
        http_port = find_free_tcp_port()
        return [
            self.proxy_path,
            "--quiet",
            f"--address={self.host}",
            f"--port={self.port}",
            f"--http-address={self.host}",
            f"--http-port={http_port}",
            f"--quota-project={self.project_id}",
            self.connection_name,
        ]

    def start(self) -> None:
        require_commands([self.proxy_path])
        self.port = self.requested_port or find_free_tcp_port()
        if not 1 <= self.port <= 65535:
            raise InfraError("Cloud SQL Auth Proxy port must be between 1 and 65535.")

        if self.requested_port is not None:
            try:
                with socket.create_connection((self.host, self.port), timeout=0.5):
                    raise InfraError(
                        f"Port {self.port} is already accepting connections; "
                        "choose another port for the Cloud SQL Auth Proxy."
                    )
            except OSError:
                pass

        self._stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                self._command(),
                stdout=subprocess.DEVNULL,
                stderr=self._stderr,
                text=True,
            )
        except FileNotFoundError:
            self._close_stderr()
            raise InfraError(
                f"Required executable not found: {self.proxy_path}"
            ) from None

        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                detail = _read_stderr(self._stderr)
                message = (
                    "Cloud SQL Auth Proxy exited before accepting connections "
                    f"(exit code {self._process.returncode})."
                )
                if detail:
                    message = f"{message}\n{detail}"
                raise InfraError(message)
            try:
                with socket.create_connection((self.host, self.port), timeout=1):
                    if self._process is not None and self._process.poll() is None:
                        return
            except OSError:
                pass
            time.sleep(0.5)

        detail = _read_stderr(self._stderr)
        self.stop()
        message = "Cloud SQL Auth Proxy did not accept connections before the timeout."
        if detail:
            message = f"{message}\n{detail}"
        raise InfraError(message)

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._close_stderr()

    def _close_stderr(self) -> None:
        if self._stderr is not None:
            try:
                self._stderr.close()
            finally:
                self._stderr = None


def run_psql(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    sql: str,
    psql_path: str = "psql",
) -> None:
    require_commands([psql_path])
    register_secret(password)
    env = {
        "PGPASSWORD": password,
        "PGSSLMODE": "disable",
        "PGCONNECT_TIMEOUT": "10",
        "PGAPPNAME": "sabor-da-terra-infra",
    }
    command = [
        psql_path,
        "-X",
        "-q",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        user,
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-v",
        "VERBOSITY=terse",
        "-f",
        "-",
    ]
    result = run_command(
        command,
        env=env,
        input_text=sql,
        check=False,
        capture_output=True,
        secrets=[password],
    )
    if result.returncode != 0:
        raise command_failure(result, "PostgreSQL command")


def run_sql_with_proxy(
    project_id: str,
    connection_name: str,
    database_name: str,
    user: str,
    password: str,
    sql: str,
    *,
    proxy_path: str = "cloud-sql-proxy",
    psql_path: str = "psql",
) -> None:
    with CloudSqlProxy(
        project_id,
        connection_name,
        proxy_path=proxy_path,
    ) as proxy:
        assert proxy.port is not None
        run_psql(
            host=proxy.host,
            port=proxy.port,
            user=user,
            password=password,
            database=database_name,
            sql=sql,
            psql_path=psql_path,
        )


def connection_name(project_id: str, region: str, instance_name: str) -> str:
    return f"{project_id}:{region}:{instance_name}"
