"""The names that psychopy_filly.gltf_info reads from glTF files. No display and no filly needed."""

import json
import struct
from pathlib import Path

import builder_helpers
from psychopy_filly import gltf_info


def test_cube_contents(tmp_path):
    builder_helpers.write_cube(tmp_path / "cube.glb")
    builder_helpers.write_cube_gltf(tmp_path)
    for name in ("cube.glb", "cube.gltf"):
        contents = gltf_info.contents(tmp_path / name)
        assert [(item.key, item.label) for item in contents.animations] == [("spin", "spin  (2.00 s)")]
        assert [item.key for item in contents.variants] == ["red"]
        assert [item.key for item in contents.materials] == ["painted", "red"]
        assert [item.key for item in contents.cameras] == ["front"]
        assert contents.nodes == [(0, 0, "cube [0] mesh"), (0, 1, "front [1] camera")]


def test_unnamed_items_skins_morphs_and_tree(tmp_path):
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "root", "children": [1, 3]}, {"name": "hip", "children": [2]}, {},
                  {"mesh": 0, "skin": 0, "camera": 0,
                   "extensions": {"KHR_lights_punctual": {"light": 0}}}],
        "meshes": [{"primitives": [{"attributes": {}, "targets": [{}, {}]}], "extras": {"targetNames": ["smile", "blink"]}}],
        "skins": [{"joints": [1, 2]}],
        "materials": [{}],
        "accessors": [{"max": [1.5]}, {"max": [0.25]}],
        "animations": [{"samplers": [{"input": 0}, {"input": 1}]}],
    }
    (tmp_path / "model.gltf").write_text(json.dumps(document))
    contents = gltf_info.contents(tmp_path / "model.gltf")
    # Unnamed items take their glTF index, which filly accepts as a key.
    assert [(item.key, item.label) for item in contents.animations] == [("0", "animation 0 (no name)  (1.50 s)")]
    assert [item.key for item in contents.materials] == ["0"]
    assert [item.key for item in contents.cameras] == ["3"]
    assert [item.key for item in contents.lights] == ["3"]
    assert contents.skins == [("skin 0", ["hip", "node 2"])]
    assert contents.morph_targets == [("mesh 0", ["smile", "blink"])]
    assert contents.nodes == [(0, 0, "root [0]"), (1, 1, "hip [1]"), (2, 2, "node 2 [2]"),
                              (1, 3, "node 3 [3] mesh camera skinned light")]
    text = gltf_info.summary(contents, "model.gltf")
    assert "Skins and their bones (1)\n    skin 0: hip, node 2\n" in text
    assert "Material variants: none\n" in text


def test_glb_reads_only_the_json_chunk(tmp_path):
    # A truncated binary chunk does not matter: the reader stops after the JSON.
    encoded = json.dumps({"asset": {"version": "2.0"}, "animations": [{"name": "a", "samplers": []}]}).encode()
    encoded += b" " * (-len(encoded) % 4)
    data = (struct.pack("<III", 0x46546C67, 2, 1 << 30) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", 1 << 29, 0x004E4942) + b"\0" * 16)
    (tmp_path / "big.glb").write_bytes(data)
    assert [item.key for item in gltf_info.contents(tmp_path / "big.glb").animations] == ["a"]


def test_contents_follow_file_changes(tmp_path):
    path = tmp_path / "model.gltf"
    path.write_text(json.dumps({"asset": {"version": "2.0"}, "materials": [{"name": "a"}]}))
    assert [item.key for item in gltf_info.contents(path).materials] == ["a"]
    path.write_text(json.dumps({"asset": {"version": "2.0"}, "materials": [{"name": "b"}, {"name": "c"}]}))
    assert [item.key for item in gltf_info.contents(path).materials] == ["b", "c"]


def test_command_line(tmp_path, capsys):
    builder_helpers.write_cube(tmp_path / "cube.glb")
    gltf_info.main([str(tmp_path / "cube.glb")])
    output = capsys.readouterr().out
    assert "Animations (1)\n    spin  (2.00 s)\n" in output
