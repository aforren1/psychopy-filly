"""The names in a glTF file: animations, variants, materials, cameras, lights, skins, and nodes.

This module reads only the glTF JSON, without filly, so that Builder can use it where filly is not
installed. A .glb file is read only up to the end of its JSON chunk.
"""

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A


@dataclass(frozen=True)
class Item:
    """One selectable entry. `key` is the value that the component parameter takes."""
    key: str
    label: str


@dataclass(frozen=True)
class Contents:
    animations: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    cameras: list = field(default_factory=list)
    lights: list = field(default_factory=list)
    skins: list = field(default_factory=list)  # (name, [joint node names])
    morph_targets: list = field(default_factory=list)  # (mesh name, [target names])
    nodes: list = field(default_factory=list)  # (depth, node index, label)


_cache = {}


def read_document(path):
    """Return the glTF JSON of a .glb or .gltf file as a dict."""
    path = Path(path)
    with path.open("rb") as file:
        header = file.read(20)
        if len(header) >= 20 and struct.unpack_from("<I", header)[0] == GLB_MAGIC:
            length, kind = struct.unpack_from("<II", header, 12)
            if kind != JSON_CHUNK:
                raise ValueError(f"{path.name}: the first GLB chunk is not JSON")
            return json.loads(file.read(length))
        return json.loads(header + file.read())


def contents(path):
    """Return the `Contents` of a glTF file. Results are cached until the file changes."""
    path = Path(path)
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _cache.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    result = _contents(read_document(path))
    _cache[path] = (stamp, result)
    return result


def _name(entry, kind, index):
    name = entry.get("name")
    return (name, name) if name else (str(index), f"{kind} {index} (no name)")


def _contents(document):
    accessors = document.get("accessors", [])
    nodes = document.get("nodes", [])
    meshes = document.get("meshes", [])

    animations = []
    for index, animation in enumerate(document.get("animations", [])):
        # The specification requires min and max on animation input accessors.
        times = [accessors[sampler["input"]].get("max", [0])[0]
                 for sampler in animation.get("samplers", []) if sampler.get("input", -1) < len(accessors)]
        key, label = _name(animation, "animation", index)
        animations.append(Item(key, f"{label}  ({max(times, default=0):.2f} s)"))

    variants = [Item(*_name(variant, "variant", index)) for index, variant in enumerate(
        document.get("extensions", {}).get("KHR_materials_variants", {}).get("variants", []))]
    materials = [Item(*_name(material, "material", index))
                 for index, material in enumerate(document.get("materials", []))]
    # filly selects a file camera by the name or index of the node that carries it.
    cameras = [Item(*_name(node, "node", index)) for index, node in enumerate(nodes) if "camera" in node]
    lights = [Item(*_name(node, "node", index)) for index, node in enumerate(nodes)
              if "KHR_lights_punctual" in node.get("extensions", {})]

    def node_name(index):
        return nodes[index].get("name") or f"node {index}" if index < len(nodes) else f"node {index}"

    skins = [(skin.get("name") or f"skin {index}", [node_name(joint) for joint in skin.get("joints", [])])
             for index, skin in enumerate(document.get("skins", []))]
    morph_targets = []
    for index, mesh in enumerate(meshes):
        count = max((len(primitive.get("targets", [])) for primitive in mesh.get("primitives", [])), default=0)
        if count:
            names = mesh.get("extras", {}).get("targetNames") or [str(i) for i in range(count)]
            morph_targets.append((mesh.get("name") or f"mesh {index}", list(names)))

    tree = []
    roots = set(range(len(nodes))) - {child for node in nodes for child in node.get("children", [])}
    scenes = document.get("scenes", [])
    scene = scenes[document.get("scene", 0)] if scenes else {"nodes": sorted(roots)}
    seen = set()

    def walk(index, depth):
        if index in seen or index >= len(nodes):
            return
        seen.add(index)
        node = nodes[index]
        parts = [node_name(index), f"[{index}]"]
        if "mesh" in node:
            parts.append("mesh")
        if "camera" in node:
            parts.append("camera")
        if "skin" in node:
            parts.append("skinned")
        if "KHR_lights_punctual" in node.get("extensions", {}):
            parts.append("light")
        tree.append((depth, index, " ".join(parts)))
        for child in node.get("children", []):
            walk(child, depth + 1)

    for root in scene.get("nodes", []):
        walk(root, 0)
    return Contents(animations, variants, materials, cameras, lights, skins, morph_targets, tree)


def summary(contents, title):
    """Return a plain-text description of `contents`."""
    lines = [title, ""]

    def section(heading, items):
        lines.append(f"{heading} ({len(items)})" if items else f"{heading}: none")
        lines.extend(f"    {item}" for item in items)
        lines.append("")

    section("Animations", [item.label for item in contents.animations])
    section("Material variants", [item.label for item in contents.variants])
    section("Materials", [item.label for item in contents.materials])
    section("Camera nodes", [item.label for item in contents.cameras])
    section("Light nodes", [item.label for item in contents.lights])
    section("Morph targets", [f"{mesh}: {', '.join(names)}" for mesh, names in contents.morph_targets])
    section("Skins and their bones", [f"{name}: {', '.join(joints)}" for name, joints in contents.skins])
    section("Nodes", ["    " * depth + label for depth, _, label in contents.nodes])
    return "\n".join(lines).rstrip() + "\n"


def show(*paths):
    """Print the contents of glTF files. In the Shell of PsychoPy's Coder window:

    >>> from psychopy_filly import gltf_info
    >>> gltf_info.show(r"C:\\experiment\\model.glb")
    """
    for path in paths:
        print(summary(contents(path), str(path)))


def main(argv=None):
    """Print the contents of glTF files: python -m psychopy_filly.gltf_info FILE [FILE ...]"""
    import argparse
    parser = argparse.ArgumentParser(prog="python -m psychopy_filly.gltf_info",
                                     description="List the animations, variants, materials, cameras, "
                                                 "lights, morph targets, skins, and nodes of glTF files.")
    parser.add_argument("files", nargs="+", type=Path)
    show(*parser.parse_args(argv).files)


if __name__ == "__main__":
    main()
