from common import base_parser, main_entry


def deploy(config: dict) -> None:
    raise NotImplementedError("Deployment is implemented in a later infrastructure block.")


if __name__ == "__main__":
    main_entry(base_parser("Build and deploy the Sabor da Terra application"), deploy)
