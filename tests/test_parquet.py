import awkward as ak
import fsspec
import pyarrow as pa
import pyarrow.dataset as pad
import pytest

import dask_awkward as dak
from dask_awkward.lib.io.parquet import _metadata_file_from_data_files, to_parquet

if pa.__version__.split(".") < ["6"]:
    pytest.skip("Needs pyarrow 6")

data = [[1, 2, 3], [4, None], None]
arr = pa.array(data)
ds = pa.Table.from_arrays([arr], names=["arr"])
fs = fsspec.filesystem("file")
sample = (
    "https://github.com/scikit-hep/awkward-1.0/raw/main/tests/"
    "samples/nullable-record-primitives-simple.parquet"
)
deep = ak.Array({"arr": [{"a": [1, 2, 3], "b": [3, 4, 5]}] * 4})
ds_deep = pa.Table.from_arrays(
    [ak.to_arrow(deep, extensionarray=False, list_to32=True)], names=["arr"]
)


@pytest.mark.parametrize("ignore_metadata", [True, False])
@pytest.mark.parametrize("scan_files", [True, False])
def test_remote_single(ignore_metadata, scan_files):
    arr = dak.from_parquet(
        sample, ignore_metadata=ignore_metadata, scan_files=scan_files
    )
    assert arr.compute().to_list() == [
        {"u4": None, "u8": 1},
        {"u4": None, "u8": 2},
        {"u4": None, "u8": 3},
        {"u4": None, "u8": 4},
        {"u4": None, "u8": 5},
    ]


@pytest.mark.parametrize("ignore_metadata", [True, False])
@pytest.mark.parametrize("scan_files", [True, False])
def test_remote_double(ignore_metadata, scan_files):
    arr = dak.from_parquet(
        [sample, sample], ignore_metadata=ignore_metadata, scan_files=scan_files
    )
    assert arr.npartitions == 2
    assert (
        arr.compute().to_list()
        == [
            {"u4": None, "u8": 1},
            {"u4": None, "u8": 2},
            {"u4": None, "u8": 3},
            {"u4": None, "u8": 4},
            {"u4": None, "u8": 5},
        ]
        * 2
    )


@pytest.mark.parametrize("ignore_metadata", [True, False])
@pytest.mark.parametrize("scan_files", [True, False])
def test_dir_of_one_file(tmpdir, ignore_metadata, scan_files):
    pad.write_dataset(ds, tmpdir, format="parquet")
    arr = dak.from_parquet(
        tmpdir, ignore_metadata=ignore_metadata, scan_files=scan_files
    )
    assert arr["arr"].compute().to_list() == data


@pytest.mark.parametrize("ignore_metadata", [True, False])
@pytest.mark.parametrize("scan_files", [True, False])
def test_dir_of_one_file_metadata(tmpdir, ignore_metadata, scan_files):
    tmpdir = str(tmpdir)

    pad.write_dataset(ds, tmpdir, format="parquet")
    _metadata_file_from_data_files(["/".join([tmpdir, "part-0.parquet"])], fs, tmpdir)

    arr = dak.from_parquet(
        tmpdir, ignore_metadata=ignore_metadata, scan_files=scan_files
    )
    assert arr["arr"].compute().to_list() == data


@pytest.mark.parametrize("ignore_metadata", [True, False])
@pytest.mark.parametrize("scan_files", [True, False])
def test_dir_of_two_files(tmpdir, ignore_metadata, scan_files):
    tmpdir = str(tmpdir)
    paths = ["/".join([tmpdir, _]) for _ in ["part-0.parquet", "part-1.parquet"]]
    pad.write_dataset(ds, tmpdir, format="parquet")
    fs.cp(paths[0], paths[1])
    arr = dak.from_parquet(
        tmpdir, ignore_metadata=ignore_metadata, scan_files=scan_files
    )
    assert arr["arr"].compute().to_list() == data * 2


@pytest.mark.parametrize("ignore_metadata", [True, False])
@pytest.mark.parametrize("scan_files", [True, False])
def test_dir_of_two_files_metadata(tmpdir, ignore_metadata, scan_files):
    tmpdir = str(tmpdir)
    paths = ["/".join([tmpdir, _]) for _ in ["part-0.parquet", "part-1.parquet"]]
    pad.write_dataset(ds, tmpdir, format="parquet")
    fs.cp(paths[0], paths[1])
    _metadata_file_from_data_files(paths, fs, tmpdir)

    arr = dak.from_parquet(
        tmpdir, ignore_metadata=ignore_metadata, scan_files=scan_files
    )
    assert arr["arr"].compute().to_list() == data * 2


def test_columns(tmpdir):
    tmpdir = str(tmpdir)
    pad.write_dataset(ds_deep, tmpdir, format="parquet")
    arr = dak.from_parquet(tmpdir)
    arr2 = dak.from_parquet(tmpdir, columns=["arr.arr.a"])
    arr3 = dak.from_parquet(tmpdir, columns=["arr.arr.b"])

    assert arr.arr.arr.a.compute().tolist() == arr2.arr.arr.a.compute().tolist()
    assert arr.arr.arr.b.compute().tolist() == arr3.arr.arr.b.compute().tolist()

    assert arr.arr.arr.fields == ["a", "b"]
    assert arr2.arr.arr.fields == ["a"]
    assert arr3.arr.arr.fields == ["b"]


def test_write_simple(tmpdir):
    import os

    import pyarrow.parquet as pq

    tmpdir = str(tmpdir)
    arr = dak.from_awkward(ak.from_iter(data), 2)
    to_parquet(arr, tmpdir)
    files = fs.ls(tmpdir)
    assert [os.path.basename(_) for _ in sorted(files)] == [
        "part0.parquet",
        "part1.parquet",
    ]
    t = pq.read_table(tmpdir).to_pydict()
    if "data" in t:
        assert t["data"] == data
    else:
        assert t[""] == data


def test_write_roundtrip(tmpdir):
    tmpdir = str(tmpdir)
    arr = dak.from_awkward(ak.from_iter(data), 2)
    to_parquet(arr, tmpdir)
    arr = dak.from_parquet(tmpdir)
