"""Local SVG tracing, live-text overlay, and strict flat-vector inspection."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
GEOMETRY = {"path", "circle", "ellipse", "rect", "polygon", "polyline", "line"}
ALLOWED = GEOMETRY | {"svg", "g", "defs", "title", "desc", "metadata", "text", "tspan"}
EFFECTS = {"mask", "clipPath", "linearGradient", "radialGradient", "filter", "pattern", "use", "style"}
EFFECT_PROPERTIES = {"mask", "clip-path", "filter", "mix-blend-mode"}
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _load_svg(path: Path) -> ET.Element:
    content = path.read_text(encoding="utf-8-sig")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", content, re.I):
        raise ValueError("DTD and entity declarations are not supported")
    if re.search(r"<\?(?!xml\s)[\s\S]*?\?>", content, re.I):
        raise ValueError("Processing instructions, including XML stylesheets, are not supported")
    root = ET.fromstring(content)
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("Expected an SVG root in the SVG namespace")
    return root


def _style(node: ET.Element) -> dict[str, str]:
    result = dict(node.attrib)
    for declaration in node.get("style", "").split(";"):
        if not declaration.strip():
            continue
        if ":" not in declaration:
            raise ValueError("Malformed inline style")
        key, value = declaration.split(":", 1)
        result[key.strip().lower()] = value.strip()
    return result


def _opacity(value: str) -> float:
    result = _number(value[:-1], "opacity") / 100 if value.endswith("%") else _number(value, "opacity")
    if not 0 <= result <= 1:
        raise ValueError("Opacity must be between 0 and 1")
    return result


def _paint_alpha(value: str) -> float:
    value = value.strip().lower()
    if value == "transparent":
        return 0
    if re.fullmatch(r"#[0-9a-f]{4}", value):
        return int(value[-1] * 2, 16) / 255
    if re.fullmatch(r"#[0-9a-f]{8}", value):
        return int(value[-2:], 16) / 255
    if value.startswith(("rgba(", "hsla(")):
        return _opacity(re.split(r"[,/]", value[:-1])[-1].strip())
    if "/" in value or "var(" in value or "currentcolor" in value:
        raise ValueError("Resolve indirect or modern CSS paint colors to explicit opaque colors")
    return 1


def inspect(svg: Path, expected_text: int | None = None) -> dict:
    root = _load_svg(svg)
    counts: dict[str, int] = {}
    errors: list[str] = []
    transparent_geometry = path_commands = external_references = event_handlers = raster_nodes = unsupported = 0

    def visit(node: ET.Element, group_opacity: float, inherited: dict[str, str]) -> None:
        nonlocal transparent_geometry, path_commands, external_references, event_handlers, raster_nodes, unsupported
        name = _name(node.tag)
        counts[name] = counts.get(name, 0) + 1
        if node.tag != f"{{{SVG_NS}}}{name}" or name not in ALLOWED:
            errors.append(f"Unsupported element: {name}")
        raster_nodes += name == "image"
        unsupported += name in EFFECTS
        for key, value in node.attrib.items():
            local = _name(key).lower()
            if local.startswith("on"):
                event_handlers += 1
                errors.append(f"Event handler is forbidden: {local}")
            if local == "href" and not value.startswith("#"):
                external_references += 1
                errors.append("External/data resource reference is forbidden")
            if re.search(r"url\s*\(", value, re.I):
                errors.append("URL paint/effect references are not supported")
            if local == "class":
                errors.append("CSS classes are not supported; use explicit properties")
        props = _style(node)
        for key in EFFECT_PROPERTIES:
            if key in props and props[key] not in {"none", "normal"}:
                errors.append(f"Unsupported visual property: {key}")
        cumulative = group_opacity * _opacity(props.get("opacity", "1"))
        inherited_now = inherited | {key: props[key] for key in ("fill-opacity", "stroke-opacity", "fill", "stroke") if key in props}
        fill_opacity = _opacity(inherited_now.get("fill-opacity", "1"))
        stroke_opacity = _opacity(inherited_now.get("stroke-opacity", "1"))
        if name in GEOMETRY:
            has_fill = inherited_now.get("fill", "black") != "none" and name != "line"
            has_stroke = inherited_now.get("stroke", "none") != "none"
            transparent_geometry += bool(
                (has_fill and cumulative * fill_opacity * _paint_alpha(inherited_now.get("fill", "black")) < 1)
                or (has_stroke and cumulative * stroke_opacity * _paint_alpha(inherited_now.get("stroke", "none")) < 1)
            )
        if name == "path":
            path_commands += len(re.findall(r"[MmLlHhVvCcSsQqTtAaZz]", node.get("d", "")))
        for child in node:
            visit(child, cumulative, inherited_now)

    visit(root, 1, {})
    if transparent_geometry:
        errors.append("Transparent geometry is outside the flat-vector contract")
    text_count = counts.get("text", 0)
    if expected_text is not None and text_count != expected_text:
        errors.append(f"Expected {expected_text} live text objects; found {text_count}")
    errors = list(dict.fromkeys(errors))
    return {
        "file": str(svg.resolve()), "status": "FAIL" if errors else "PASS", "counts": counts,
        "vector_element_count": sum(counts.get(name, 0) for name in GEOMETRY),
        "path_command_count": path_commands, "text_count": text_count, "raster_node_count": raster_nodes,
        "text_contents": ["".join(node.itertext()) for node in root.iter() if _name(node.tag) == "text"],
        "external_reference_count": external_references, "event_handler_count": event_handlers,
        "unsupported_visual_effect_count": unsupported, "geometry_opacity_count": transparent_geometry, "errors": errors,
    }


def _require_clean(path: Path, expected_text: int | None = None) -> dict:
    report = inspect(path, expected_text)
    if report["errors"]:
        raise ValueError("; ".join(report["errors"]))
    return report


def _new_output(output: Path, inputs: tuple[Path, ...]) -> None:
    if output.resolve() in {path.resolve() for path in inputs}:
        raise ValueError("Output cannot overwrite an input")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")


def _write_new(output: Path, content: bytes, inputs: tuple[Path, ...] = ()) -> None:
    _new_output(output, inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(content)


def _canvas(root: ET.Element) -> tuple[float, float]:
    dimensions = []
    for attr in ("width", "height"):
        match = re.fullmatch(f"({NUMBER.pattern})(?:px)?", root.get(attr, "").strip())
        if not match:
            raise ValueError("Merge requires explicit numeric/px SVG width and height")
        dimensions.append(_number(match.group(1), attr))
    if min(dimensions) <= 0:
        raise ValueError("SVG dimensions must be positive")
    if root.get("viewBox") is not None:
        values = [_number(value, "viewBox") for value in re.split(r"[\s,]+", root.get("viewBox").strip())]
        if len(values) != 4 or values[:2] != [0, 0] or values[2:] != dimensions:
            raise ValueError("Merge requires a zero-based viewBox matching width/height in pixels")
    return dimensions[0], dimensions[1]


def merge_text(svg: Path, manifest: Path, output: Path) -> dict:
    """Overlay labels above all geometry; y is the first text baseline."""
    _new_output(output, (svg, manifest))
    _require_clean(svg, 0)
    root = _load_svg(svg)
    width, height = _canvas(root)
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    canvas = data["canvas"]
    if (_number(canvas["width"], "canvas.width"), _number(canvas["height"], "canvas.height")) != (width, height):
        raise ValueError("Manifest and SVG dimensions differ; coordinate scaling must be explicit")
    space = canvas["coordinate_space"]
    if space not in {"pixel", "normalized"}:
        raise ValueError("coordinate_space must be pixel or normalized")
    elements = data["text_elements"]
    if not isinstance(elements, list):
        raise ValueError("text_elements must be an array")
    elements = sorted(elements, key=lambda item: _number(item.get("paint_order", 0), "paint_order"))
    existing_ids = {node.get("id") for node in root.iter() if node.get("id")}
    if "live-text-overlay" in existing_ids:
        raise ValueError("live-text-overlay ID already exists")
    existing_ids.add("live-text-overlay")
    group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "live-text-overlay"})
    for index, item in enumerate(elements):
        content = item["content"]
        if not isinstance(content, str):
            raise ValueError("Text content must be a string")
        x, y = (_number(item[key], key) for key in ("x", "y"))
        if not (0 <= x <= (1 if space == "normalized" else width) and 0 <= y <= (1 if space == "normalized" else height)):
            raise ValueError("Text anchor lies outside the declared canvas")
        if space == "normalized":
            x, y = x * width, y * height
        size = _number(item["font_size"], "font_size")
        font_space = item.get("font_size_space", "pixel")
        if font_space not in {"pixel", "normalized"} or size <= 0:
            raise ValueError("font_size must be positive; font_size_space must be pixel or normalized")
        if font_space == "normalized":
            size *= height
        line_height = _number(item.get("line_height", 1.2), "line_height")
        if line_height <= 0:
            raise ValueError("line_height must be positive")
        anchor = item.get("text_anchor", "start")
        if anchor not in {"start", "middle", "end"}:
            raise ValueError("text_anchor must be start, middle, or end")
        label_id = str(item.get("id", f"label-{index + 1}"))
        if not label_id or label_id in existing_ids:
            raise ValueError(f"Duplicate or empty text ID: {label_id}")
        existing_ids.add(label_id)
        attrs = {
            "id": label_id, "x": f"{x:g}", "y": f"{y:g}", "font-size": f"{size:g}",
            "font-family": str(item.get("font_family", "Arial")), "font-weight": str(item.get("font_weight", "400")),
            "font-style": str(item.get("font_style", "normal")), "fill": str(item.get("fill", "#111111")),
            "text-anchor": anchor, "{http://www.w3.org/XML/1998/namespace}space": "preserve",
        }
        rotation = _number(item.get("rotation", 0), "rotation")
        if rotation:
            attrs["transform"] = f"rotate({rotation:g} {x:g} {y:g})"
        text = ET.SubElement(group, f"{{{SVG_NS}}}text", attrs)
        for row, line in enumerate(content.split("\n")):
            ET.SubElement(text, f"{{{SVG_NS}}}tspan", {"x": f"{x:g}", "y": f"{y + row * size * line_height:g}"}).text = line
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with tempfile.TemporaryDirectory(prefix="svg-merge-") as temporary:
        candidate = Path(temporary) / "candidate.svg"
        candidate.write_bytes(payload)
        _require_clean(candidate, len(elements))
    _write_new(output, payload, (svg, manifest))
    return inspect(output, len(elements))


def trace(input_png: Path, output_dir: Path, mode: str = "both") -> dict:
    """Generate independent candidates; do not infer semantic colors or a winner."""
    if mode not in {"faithful", "flat", "both"}:
        raise ValueError("mode must be faithful, flat, or both")
    _new_output(output_dir, (input_png,))
    try:
        from PIL import Image
        import vtracer
    except ImportError as exc:
        raise RuntimeError("Trace requires optional dependencies: pip install Pillow vtracer") from exc
    with Image.open(input_png) as original:
        if original.format != "PNG":
            raise ValueError("Trace input must be PNG")
        rgba = original.convert("RGBA")
        if rgba.getextrema()[3] != (255, 255):
            raise ValueError("Trace requires an opaque PNG; choose the background explicitly first")
        image = original.convert("RGB")
    output_dir.mkdir(parents=True, exist_ok=False)
    reports = {}
    for candidate_mode in (["faithful", "flat"] if mode == "both" else [mode]):
        with tempfile.TemporaryDirectory(prefix="svg-trace-") as temporary:
            source, target = Path(temporary) / "input.png", Path(temporary) / "trace.svg"
            prepared = image if candidate_mode == "faithful" else image.quantize(colors=24, dither=Image.Dither.NONE).convert("RGB")
            prepared.save(source)
            vtracer.convert_image_to_svg_py(
                str(source), str(target), colormode="color", hierarchical="cutout", mode="spline",
                filter_speckle=2 if candidate_mode == "faithful" else 4,
                color_precision=8 if candidate_mode == "faithful" else 6,
                layer_difference=8 if candidate_mode == "faithful" else 24,
                corner_threshold=60, length_threshold=3.0 if candidate_mode == "faithful" else 4.0,
                max_iterations=10, splice_threshold=45, path_precision=3 if candidate_mode == "faithful" else 2,
            )
            _require_clean(target, 0)
            output = output_dir / f"{candidate_mode}-geometry.svg"
            _write_new(output, target.read_bytes(), (input_png,))
            reports[candidate_mode] = inspect(output, 0)
    report = {"input": str(input_png.resolve()), "selection": "visual_review_required", "candidates": reports}
    _write_new(output_dir / "trace-report.json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("inspect")
    check.add_argument("svg", type=Path)
    check.add_argument("--expected-text", type=int)
    merge = commands.add_parser("merge-text")
    merge.add_argument("--svg", type=Path, required=True)
    merge.add_argument("--manifest", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    tracing = commands.add_parser("trace")
    tracing.add_argument("--input", dest="input_png", type=Path, required=True)
    tracing.add_argument("--output-dir", type=Path, required=True)
    tracing.add_argument("--mode", choices=["faithful", "flat", "both"], default="both")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            report = inspect(args.svg, args.expected_text)
        elif args.command == "merge-text":
            report = merge_text(args.svg, args.manifest, args.output)
        else:
            report = trace(args.input_png, args.output_dir, args.mode)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if report.get("status") == "FAIL" else 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ET.ParseError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
