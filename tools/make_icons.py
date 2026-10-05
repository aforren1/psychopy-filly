"""Write the placeholder component icons in the classic, light, and dark themes: an isometric cube
for 3D Model, and a smaller cube in viewfinder corners for 3D Scene.

Run with any Python that has Pillow:  python tools/make_icons.py
Replace these with designed icons before a release.
"""

from pathlib import Path

from PIL import Image, ImageDraw

COMPONENTS = Path(__file__).resolve().parents[1] / "psychopy_filly" / "components"

# (top, left, right face fill, outline) per theme. Light and dark use the grays and the blue
# accent of the built-in PsychoPy component icons.
THEMES = {
    "classic": ((170, 205, 245, 255), (111, 165, 233, 255), (60, 110, 190, 255), (30, 60, 110, 255)),
    "light": ((242, 242, 242, 255), (2, 169, 234, 255), (102, 102, 110, 255), (102, 102, 110, 255)),
    "dark": ((242, 242, 242, 255), (2, 169, 234, 255), (172, 172, 176, 255), (172, 172, 176, 255)),
}

# The cube's corners on a 32 x 32 grid.
CUBE = {"n": (16, 4), "e": (27, 10), "c": (16, 16), "w": (5, 10), "sw": (5, 22), "s": (16, 28), "se": (27, 22)}
# The scene icon's cube: the same cube at 60% size about the center.
SMALL = {k: (16 + (x - 16) * 0.6, 16 + (y - 16) * 0.6) for k, (x, y) in CUBE.items()}
# Viewfinder corners: (x, y) of the corner and the directions of its two arms.
CORNERS = [((3, 3), 1, 1), ((29, 3), -1, 1), ((3, 29), 1, -1), ((29, 29), -1, -1)]
ARM = 7


def svg(name, points, corners):
    def path(*keys):
        return "M" + " L".join(f"{points[k][0]:g},{points[k][1]:g}" for k in keys) + " Z"
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<svg width="100%" height="100%" viewBox="0 0 32 32" version="1.1" xmlns="http://www.w3.org/2000/svg">',
        f'    <g id="{name}" style="stroke:currentColor;stroke-width:1.2;stroke-linejoin:round;">',
        f'        <path d="{path("n", "e", "c", "w")}" style="fill:rgb(242,242,242);"/>',
        f'        <path d="{path("w", "c", "s", "sw")}" style="fill:rgb(2,169,234);"/>',
        f'        <path d="{path("e", "c", "s", "se")}" style="fill:rgb(102,102,110);"/>',
    ]
    for (x, y), dx, dy in corners:
        lines.append(f'        <path d="M{x + dx * ARM},{y} L{x},{y} L{x},{y + dy * ARM}" style="fill:none;"/>')
    lines += ["    </g>", "</svg>", ""]
    return "\n".join(lines)


def icon(size, points, corners, top, left, right, outline):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size / 32
    p = {k: (x * s, y * s) for k, (x, y) in points.items()}
    width = max(1, round(1.2 * s))
    draw.polygon([p["n"], p["e"], p["c"], p["w"]], fill=top, outline=outline, width=width)
    draw.polygon([p["w"], p["c"], p["s"], p["sw"]], fill=left, outline=outline, width=width)
    draw.polygon([p["e"], p["c"], p["s"], p["se"]], fill=right, outline=outline, width=width)
    for (x, y), dx, dy in corners:
        draw.line([((x + dx * ARM) * s, y * s), (x * s, y * s), (x * s, (y + dy * ARM) * s)],
                  fill=outline, width=width, joint="curve")
    return image


def main():
    for stem, name, points, corners in (("model3d", "Model3DComponent", CUBE, []),
                                        ("scene3d", "Scene3DComponent", SMALL, CORNERS)):
        out = COMPONENTS / stem
        for theme, colors in THEMES.items():
            folder = out / theme
            folder.mkdir(parents=True, exist_ok=True)
            icon(48, points, corners, *colors).save(folder / f"{stem}.png")
            icon(96, points, corners, *colors).save(folder / f"{stem}@2x.png")
        (out / f"{stem}.svg").write_text(svg(name, points, corners), encoding="utf-8")


if __name__ == "__main__":
    main()
