import unittest
from os.path import exists, join
from pathlib import Path

from faim_hcs.io.MolecularDevicesImageXpress import (
    parse_single_plane_multi_fields,
    parse_multi_field_stacks,
)

ROOT_DIR = Path(__file__).parent.parent


class TestMolecularDevicesImageXpress(unittest.TestCase):
    def test_parse_single_plane_multi_fields(self):
        acquisition_dir = join(ROOT_DIR.parent, "resources", "MIP-2P-2sub")

        files = parse_single_plane_multi_fields(acquisition_dir=acquisition_dir)

        assert len(files) == 8
        assert files["name"].unique() == ["MIP-2P-2sub"]
        assert all(files["well"].unique() == ["C05", "C06"])
        assert all(files["field"].unique() == ["s1", "s2"])
        channels = files["channel"].unique()
        assert len(channels) == 2
        assert "w1" in channels
        assert "w2" in channels
        for item in files["path"]:
            assert exists(item)
            assert "thumb" not in item

    def test_parse_multi_field_stacks(self):
        acquisition_dir = ROOT_DIR.parent / "resources" / "Z-stack-plus-MIP-4P-4sub"

        files = parse_multi_field_stacks(acquisition_dir=acquisition_dir)

        assert len(files) == 640
        assert files["name"].unique() == ["Z-stack-plus-MIP-4P-4sub"]
        assert all(files["well"].unique() == ["C05", "C06", "C07", "C08"])
        assert all(files["field"].unique() == ["s1", "s2", "s3", "s4"])

        self.assertCountEqual(files["z"].unique(), [str(x) for x in range(1, 11)])

        self.assertCountEqual(files["channel"].unique(), ["w1", "w2", "w3", "w4"])

        for item in files["path"]:
            assert exists(item)
            assert "thumb" not in item
