import re

import empneon


def test_package_importable() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", empneon.__version__)
