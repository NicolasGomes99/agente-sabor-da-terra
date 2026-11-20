from common import base_parser, main_entry


def migrate(config: dict) -> None:
    raise NotImplementedError("Migration automation is implemented in a later infrastructure block.")


if __name__ == "__main__":
    main_entry(base_parser("Run the application database migrations"), migrate)
