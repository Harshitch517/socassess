import duckdb
import sklearn
from sklearn.cluster import HDBSCAN  # noqa: F401  (sklearn ships HDBSCAN; no extra package)

import socassess
from socassess import config


def test_package_imports():
    assert socassess.__version__


def test_paths_exist():
    assert config.DATA_RAW.is_dir()
    assert config.DATA_PROCESSED.is_dir()


def test_duckdb_in_memory():
    assert duckdb.connect().execute("select 42").fetchone()[0] == 42


def test_sklearn_version():
    major, minor = map(int, sklearn.__version__.split(".")[:2])
    assert (major, minor) >= (1, 3)
