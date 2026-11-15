import os


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        raise RuntimeError("DATABASE_URL must be set.")
    return url.strip()
