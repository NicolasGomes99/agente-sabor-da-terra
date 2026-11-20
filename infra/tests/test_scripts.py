import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deploy
import destroy
import migrate


@pytest.mark.parametrize(
    "operation",
    [migrate.migrate, deploy.deploy, destroy.destroy],
)
def test_placeholder_operation_does_not_reach_cloud(operation) -> None:
    with pytest.raises(NotImplementedError):
        operation({})
