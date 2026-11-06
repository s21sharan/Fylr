"""Smoke test to verify the pytest scaffold works."""


def test_placeholder():
    assert 1 + 1 == 2


def test_tmp_workdir_fixture(tmp_workdir):
    files = sorted(p.name for p in tmp_workdir.iterdir())
    assert files == ["alpha.txt", "bravo.txt", "charlie.txt"]
