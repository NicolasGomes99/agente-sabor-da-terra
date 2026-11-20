from common import base_parser, main_entry


def destroy(config: dict) -> None:
    raise NotImplementedError("Desprovisioning is implemented in a later infrastructure block.")


if __name__ == "__main__":
    main_entry(base_parser("Destroy the Sabor da Terra Google Cloud environment"), destroy)
