import hashlib
import inspect
from pathlib import Path
import shutil
import sys
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
CURRENT_PACKAGE = REPOSITORY_ROOT / "dist" / "falcon_bms_plugin.zip"
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

    def test_current_package_has_current_sources_and_safe_structure(self):
        self.assertTrue(CURRENT_PACKAGE.is_file())
        self.assertNotEqual(V020_SHA256, self._sha256(CURRENT_PACKAGE))

        with ZipFile(CURRENT_PACKAGE) as archive:
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
        self.assertIn('__version__ = "0.3.2"', version_source)
        self.assertIn("from .version import __version__", main_source)
        self.assertIn("version=__version__", main_source)

    def test_current_package_extracts_and_loads_with_upstream_loader(self):
        with TemporaryDirectory() as temp_dir:
            install_root = Path(temp_dir)
            with ZipFile(CURRENT_PACKAGE) as archive:
                archive.extractall(install_root)

            installed = install_root / "falcon_bms_plugin"
            module = load_user_parser_plugin(installed)
            plugin = module.ParserPlugin()
            self.assertIsInstance(plugin, PluginInterface)
            self.assertEqual("Falcon BMS", plugin.name)
            self.assertEqual("0.3.2", plugin.version)

    def test_package_upgrades_from_v020_in_the_same_process(self):
        module_prefix = "jd_user_parser_plugin_falcon_bms_plugin"
        self._clear_loaded_plugin(module_prefix)
        self.addCleanup(self._clear_loaded_plugin, module_prefix)

        with TemporaryDirectory() as temp_dir:
            install_root = Path(temp_dir)
            with ZipFile(V020_BACKUP) as archive:
                archive.extractall(install_root)

            installed = install_root / "falcon_bms_plugin"
            legacy_module = load_user_parser_plugin(installed)
            self.assertEqual("0.2.0", legacy_module.ParserPlugin().version)

            shutil.rmtree(installed)
            with ZipFile(CURRENT_PACKAGE) as archive:
                archive.extractall(install_root)

            current_module = load_user_parser_plugin(installed)
            plugin = current_module.ParserPlugin()
            self.assertEqual("0.3.2", plugin.version)
            self.assertIn(
                "show_dx_button_numbers",
                plugin.plugin_settings_model.model_fields,
            )
            self.assertIn(
                "button_layout",
                plugin.plugin_settings_model.model_fields,
            )
            self.assertIn(
                "config_dir",
                inspect.signature(current_module.BMSKeyParser).parameters,
            )

    @staticmethod
    def _clear_loaded_plugin(module_prefix):
        for module_name in list(sys.modules):
            if module_name == module_prefix or module_name.startswith(
                f"{module_prefix}."
            ):
                sys.modules.pop(module_name, None)

    @staticmethod
    def _sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()


if __name__ == "__main__":
    unittest.main()
