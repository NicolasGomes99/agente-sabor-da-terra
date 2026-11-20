from common import base_parser, main_entry


def provision(config: dict) -> None:
    raise NotImplementedError("Provisioning is implemented in the next infrastructure block.")


if __name__ == "__main__":
    main_entry(base_parser("Provision the Sabor da Terra Google Cloud environment"), provision)
