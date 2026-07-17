import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from joystick_diagrams.plugins.plugin_interface import PluginInterface
from joystick_diagrams.plugins.plugin_manager import load_user_parser_plugin


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
V020_BACKUP = (
    REPOSITORY_ROOT
    / "dist"
    / "archive"
    / "v0.2.0"
    / "falcon_bms_plugin.zip"
)
V030_PACKAGE = REPOSITORY_ROOT / "dist" / "falcon_bms_plugin.zip"
V020_SHA256 = "CFAD5E4C516B3279173F3FDFA70483C73D6483D6AD4D0FCC762DE88B02734514"

PACKAGE_SOURCES = {
    "falcon_bms_plugin/__init__.py": "falcon_bms_plugin/__init__.py",
    "falcon_bms_plugin/version.py": "falcon_bms_plugin/version.py",
    "falcon_bms_plugin/main.py": "falcon_bms_plugin/main.py",
    "falcon_bms_plugin/bms_key_parser.py": "falcon_bms_plugin/bms_key_parser.py",
    "falcon_bms_plugin/bms_axis_parser.py": "falcon_bms_plugin/bms_axis_parser.py",
    "falcon_bms_plugin/img/falcon_bms.svg": (
        "falcon_bms_plugin/img/falcon_bms.svg"
    ),
    "falcon_bms_plugin/LICENSE": "LICENSE",
}


class ReleaseArtifactTests(unittest.TestCase):
    def test_v020_backup_is_the_exact_published_package(self):
        self.assertTrue(V020_BACKUP.is_file())
        self.assertEqual(V020_SHA256, self._sha256(V020_BACKUP))

        with ZipFile(V020_BACKUP) as archive:
            init_source = archive.read(
                "falcon_bms_plugin/__init__.py"
            ).decode("utf-8")
        self.assertIn('__version__ = "0.2.0"', init_source)

    def test_v030_package_has_current_sources_and_safe_structure(self):
        self.assertTrue(V030_PACKAGE.is_file())
        self.assertNotEqual(V020_SHA256, self._sha256(V030_PACKAGE))

        with ZipFile(V030_PACKAGE) as archive:
            names = set(archive.namelist())
            self.assertEqual(set(PACKAGE_SOURCES), names)
            self.assertEqual(
                {"falcon_bms_plugin"},
                {name.split("/", 1)[0] for name in names},
            )
            self.assertFalse(
                any(
                    "__pycache__" in name
                    or name.endswith((".pyc", ".pyo"))
                    or name.startswith(("tests/", "dist/"))
                    for name in names
                )
            )

            for member, source in PACKAGE_SOURCES.items():
                self.assertEqual(
                    REPOSITORY_ROOT.joinpath(source).read_bytes(),
                    archive.read(member),
                    member,
                )

            version_source = archive.read(
                "falcon_bms_plugin/version.py"
            ).decode("utf-8")
            main_source = archive.read("falcon_bms_plugin/main.py").decode(
                "utf-8"
            )
        self.assertIn('__version__ = "0.3.0"', version_source)
        self.assertIn("from .version import __version__", main_source)
        self.assertIn("version=__version__", main_source)

    def test_v030_package_extracts_and_loads_with_upstream_loader(self):
        with TemporaryDirectory() as temp_dir:
            install_root = Path(temp_dir)
            with ZipFile(V030_PACKAGE) as archive:
                archive.extractall(install_root)

            installed = install_root / "falcon_bms_plugin"
            module = load_user_parser_plugin(installed)
            plugin = module.ParserPlugin()
            self.assertIsInstance(plugin, PluginInterface)
            self.assertEqual("Falcon BMS", plugin.name)
            self.assertEqual("0.3.0", plugin.version)

    @staticmethod
    def _sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()


if __name__ == "__main__":
    unittest.main()
