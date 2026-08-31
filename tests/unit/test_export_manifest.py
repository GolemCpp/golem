import json

from golemcpp.golem import export_manifest
from golemcpp.golem.export_manifest import ExportManifest


def write_file(tmp_path, content):
    """Put content where an export manifest goes, and name the path."""
    path = tmp_path / "@json@nlohmann@github.com.json"
    path.write_text(
        content if isinstance(content, str) else json.dumps(content), encoding="utf-8"
    )
    return str(path)


def manifest_path(tmp_path):
    return str(tmp_path / "@json@nlohmann@github.com.json")


def test_what_is_written_is_what_is_read(tmp_path):
    path = manifest_path(tmp_path)

    ExportManifest(exports={"boost": ["boost_system"]}, default=["boost"]).write(path)

    manifest = ExportManifest.read(path)

    assert manifest.exports == {"boost": ["boost_system"]}
    assert manifest.default == ["boost"]


def test_an_export_building_nothing_is_written_with_no_targets(tmp_path):
    path = manifest_path(tmp_path)

    ExportManifest(exports={"json": []}).write(path)

    assert ExportManifest.read(path).exports == {"json": []}
    assert ExportManifest.read(path).default == []


def test_a_manifest_names_the_version_it_is_written_in(tmp_path):
    path = manifest_path(tmp_path)

    ExportManifest(exports={"json": []}).write(path)

    with open(path, "r", encoding="utf-8") as filein:
        assert json.load(filein)["version"] == export_manifest.EXPORT_MANIFEST_VERSION


def test_no_file_reads_as_no_manifest(tmp_path):
    assert ExportManifest.read(manifest_path(tmp_path)) is None


def test_a_file_that_is_not_json_reads_as_no_manifest(tmp_path):
    assert ExportManifest.read(write_file(tmp_path, "{not json")) is None


def test_a_file_holding_something_other_than_fields_reads_as_no_manifest(tmp_path):
    assert ExportManifest.read(write_file(tmp_path, ["json"])) is None


def test_a_newer_version_reads_as_no_manifest(tmp_path):
    path = write_file(
        tmp_path,
        {"version": export_manifest.EXPORT_MANIFEST_VERSION + 1, "exports": {}},
    )

    assert ExportManifest.read(path) is None


def test_an_older_version_reads_as_no_manifest(tmp_path):
    # A downgrade lands on a file nothing outside it identifies, since a cache
    # root is named after the dependency and the build and never after golem.
    path = write_file(
        tmp_path,
        {"version": export_manifest.EXPORT_MANIFEST_VERSION - 1, "exports": {}},
    )

    assert ExportManifest.read(path) is None


def test_a_manifest_naming_no_version_reads_as_no_manifest(tmp_path):
    # Every manifest golem writes names one, so a file without it is not one.
    assert ExportManifest.read(write_file(tmp_path, {"exports": {}})) is None


def test_exports_written_as_something_else_read_as_no_manifest(tmp_path):
    path = write_file(
        tmp_path,
        {"version": export_manifest.EXPORT_MANIFEST_VERSION, "exports": ["json"]},
    )

    assert ExportManifest.read(path) is None


def test_a_target_that_is_not_a_name_reads_as_no_manifest(tmp_path):
    path = write_file(
        tmp_path,
        {
            "version": export_manifest.EXPORT_MANIFEST_VERSION,
            "exports": {"boost": [{"name": "boost_system"}]},
        },
    )

    assert ExportManifest.read(path) is None


def test_a_default_written_as_something_else_reads_as_no_manifest(tmp_path):
    path = write_file(
        tmp_path,
        {
            "version": export_manifest.EXPORT_MANIFEST_VERSION,
            "exports": {},
            "default": "boost",
        },
    )

    assert ExportManifest.read(path) is None
