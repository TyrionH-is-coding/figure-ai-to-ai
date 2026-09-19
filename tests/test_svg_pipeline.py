"""Run with: python -m unittest discover -s tests -v"""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "svg_pipeline.py"
SPEC = importlib.util.spec_from_file_location("svg_pipeline", SCRIPT)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class SvgPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="svg-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "geometry.svg"
        self.manifest = self.directory / "labels.json"
        self.output = self.directory / "master.svg"

    def svg(self, body, attributes='width="200" height="100" viewBox="0 0 200 100"'):
        self.source.write_text(f'<svg xmlns="{pipeline.SVG_NS}" {attributes}>{body}</svg>', encoding="utf-8")

    def labels(self, *, space="pixel", **overrides):
        label = {"id": "label", "content": "Ca²⁺ − α & <β>\n中文", "x": 50, "y": 25, "font_size": 12}
        label.update(overrides)
        self.manifest.write_text(json.dumps({"canvas": {"width": 200, "height": 100, "coordinate_space": space}, "text_elements": [label]}, ensure_ascii=False), encoding="utf-8")

    def test_clean_vector_and_expected_text_gate(self):
        self.svg('<path d="M0 0L10 10Z"/><text>A</text>')
        report = pipeline.inspect(self.source, 1)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["path_command_count"], 3)
        self.assertEqual(pipeline.inspect(self.source, 2)["status"], "FAIL")

    def test_raster_and_external_references_fail(self):
        for body in ['<image href="data:image/png;base64,AA=="/>', '<image href="secret.png"/>', '<g href="https://example.org/a"/>']:
            with self.subTest(body=body):
                self.svg(body)
                self.assertEqual(pipeline.inspect(self.source)["status"], "FAIL")

    def test_scripts_events_stylesheets_and_effects_fail(self):
        for body in ['<script/>', '<path onclick="alert(1)"/>', '<style>path{opacity:0}</style>', '<use href="#x"/>', '<defs><clipPath id="x"/></defs>', '<path fill="url(#x)"/>', '<path style="filter:blur(1px)"/>']:
            with self.subTest(body=body):
                self.svg(body)
                self.assertEqual(pipeline.inspect(self.source)["status"], "FAIL")

    def test_inherited_opacity_and_inline_style_are_audited(self):
        for body in ['<g opacity="0.5"><path/></g>', '<g style="fill-opacity:50%"><path/></g>', '<g style="opacity:.5"><g><line stroke="red"/></g></g>']:
            with self.subTest(body=body):
                self.svg(body)
                report = pipeline.inspect(self.source)
                self.assertEqual(report["geometry_opacity_count"], 1)
                self.assertEqual(report["status"], "FAIL")
        self.svg('<g fill-opacity=".5"><path fill-opacity="1"/></g>')
        self.assertEqual(pipeline.inspect(self.source)["status"], "PASS")

    def test_entities_are_rejected(self):
        self.source.write_text('<!DOCTYPE svg [<!ENTITY x "x">]><svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        with self.assertRaises(ValueError):
            pipeline.inspect(self.source)

    def test_xml_stylesheet_is_rejected(self):
        self.svg('<path/>')
        self.source.write_text('<?xml-stylesheet href="https://example.org/a.css"?>' + self.source.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaises(ValueError):
            pipeline.inspect(self.source)

    def test_inherited_paint_alpha_is_audited(self):
        for paint in ("rgba(1,2,3,.5)", "#11223380", "#1238", "transparent"):
            with self.subTest(paint=paint):
                self.svg(f'<g fill="{paint}"><path/></g>')
                self.assertEqual(pipeline.inspect(self.source)["geometry_opacity_count"], 1)

    def test_merge_preserves_unicode_and_first_baseline(self):
        self.svg('<path d="M0 0L20 20"/>')
        self.labels()
        pipeline.merge_text(self.source, self.manifest, self.output)
        root = ET.parse(self.output).getroot()
        text = root.find(f'.//{{{pipeline.SVG_NS}}}text')
        spans = list(text)
        self.assertEqual([node.text for node in spans], ["Ca²⁺ − α & <β>", "中文"])
        self.assertEqual([node.get("y") for node in spans], ["25", "39.4"])
        self.assertEqual(root[-1].get("id"), "live-text-overlay")
        self.assertEqual(pipeline.inspect(self.output)["text_contents"], ["Ca²⁺ − α & <β>中文"])

    def test_paint_order_sorts_text_only_within_overlay(self):
        self.svg('<path id="base"/>')
        self.labels()
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        original = data["text_elements"][0]
        data["text_elements"] = [original | {"id": "top", "content": "Top", "paint_order": 2}, original | {"id": "bottom", "content": "Bottom", "paint_order": 1}]
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        report = pipeline.merge_text(self.source, self.manifest, self.output)
        self.assertEqual(report["text_contents"], ["Bottom", "Top"])
        self.assertEqual(ET.parse(self.output).getroot()[0].get("id"), "base")

    def test_normalized_coordinates_and_font_size(self):
        self.svg('<path/>')
        self.labels(space="normalized", x=.5, y=.4, font_size=.1, font_size_space="normalized")
        pipeline.merge_text(self.source, self.manifest, self.output)
        text = ET.parse(self.output).getroot().find(f'.//{{{pipeline.SVG_NS}}}text')
        self.assertEqual((text.get("x"), text.get("y"), text.get("font-size")), ("100", "40", "10"))

    def test_input_and_existing_output_are_preserved(self):
        self.svg('<path/>')
        self.labels()
        original = self.source.read_bytes()
        with self.assertRaises(ValueError):
            pipeline.merge_text(self.source, self.manifest, self.source)
        self.output.write_bytes(b"USER ASSET")
        with self.assertRaises(FileExistsError):
            pipeline.merge_text(self.source, self.manifest, self.output)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.output.read_bytes(), b"USER ASSET")

    def test_ambiguous_canvas_or_outside_anchor_fails_without_output(self):
        self.labels()
        for dimensions in ['width="200mm" height="100mm"', 'width="200" height="100" viewBox="10 0 200 100"', 'width="400" height="100"']:
            with self.subTest(dimensions=dimensions):
                self.svg('<path/>', dimensions)
                with self.assertRaises(ValueError):
                    pipeline.merge_text(self.source, self.manifest, self.output)
                self.assertFalse(self.output.exists())
        self.svg('<path/>')
        self.labels(x=201)
        with self.assertRaises(ValueError):
            pipeline.merge_text(self.source, self.manifest, self.output)

    def test_merge_rejects_existing_text_or_injected_paint(self):
        self.svg('<text>existing</text>')
        self.labels()
        with self.assertRaises(ValueError):
            pipeline.merge_text(self.source, self.manifest, self.output)
        self.svg('<path/>')
        self.labels(fill="url(https://example.org/a)")
        with self.assertRaises(ValueError):
            pipeline.merge_text(self.source, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_trace_output_must_be_new(self):
        with self.assertRaises(FileExistsError):
            pipeline.trace(self.directory / "input.png", self.directory)

    def test_real_trace_and_live_text_roundtrip_when_dependencies_available(self):
        try:
            from PIL import Image, ImageDraw
            import vtracer
        except ImportError:
            self.skipTest("Optional Pillow/vtracer dependencies are not installed")
        image = Image.new("RGB", (200, 100), "white")
        drawing = ImageDraw.Draw(image)
        drawing.ellipse((50, 20, 90, 60), fill="#8fd3d2", outline="#007176", width=2)
        drawing.line((90, 40, 140, 40), fill="#555555", width=3)
        input_png = self.directory / "synthetic.png"
        image.save(input_png)
        before = input_png.read_bytes()
        report = pipeline.trace(input_png, self.directory / "traced")
        self.assertEqual(report["selection"], "visual_review_required")
        self.assertEqual(set(report["candidates"]), {"faithful", "flat"})
        self.assertTrue(all(item["status"] == "PASS" for item in report["candidates"].values()))
        self.labels()
        merged = pipeline.merge_text(self.directory / "traced" / "faithful-geometry.svg", self.manifest, self.output)
        self.assertEqual(merged["text_count"], 1)
        self.assertEqual(input_png.read_bytes(), before)

    def test_trace_rejects_alpha_without_creating_output(self):
        try:
            from PIL import Image
            import vtracer
        except ImportError:
            self.skipTest("Optional Pillow/vtracer dependencies are not installed")
        input_png = self.directory / "transparent.png"
        Image.new("RGBA", (4, 4), (255, 255, 255, 128)).save(input_png)
        output_dir = self.directory / "traced"
        with self.assertRaises(ValueError):
            pipeline.trace(input_png, output_dir)
        self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
