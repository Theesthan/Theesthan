"""Run: python -m unittest discover -s scripts"""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.error import URLError

import gen
import pixelfont


def day(d, n):
    return {"date": d, "contributionCount": n}


FAKE_RESPONSE = {
    "data": {
        "user": {
            "contributionsCollection": {
                "contributionCalendar": {
                    "totalContributions": 1284,
                    "weeks": [{"contributionDays": [
                        day("2026-10-26", 4), day("2026-10-27", 0), day("2026-10-28", 3), day("2026-10-29", 1),
                    ]}],
                }
            },
            "repositories": {
                "totalCount": 31,
                "nodes": [
                    {"languages": {"edges": [
                        {"size": 300, "node": {"name": "Python", "color": "#3572A5"}},
                        {"size": 100, "node": {"name": "TypeScript", "color": "#3178c6"}},
                    ]}},
                    {"languages": {"edges": [
                        {"size": 100, "node": {"name": "Python", "color": "#3572A5"}},
                    ]}},
                ],
            },
        }
    }
}


class PixelFontTest(unittest.TestCase):
    def test_every_glyph_is_5x7(self):
        for ch, rows in pixelfont.GLYPHS.items():
            self.assertEqual(len(rows), 7, ch)
            self.assertTrue(all(len(r) == 5 for r in rows), ch)

    def test_width(self):
        self.assertEqual(pixelfont.text_width("AB", 2), 22)

    def test_lowercase_renders_as_uppercase(self):
        out = pixelfont.text("ab", 0, 0, 2)
        self.assertIn('href="#g41"', out)
        self.assertIn('href="#g42"', out)

    def test_unknown_char_is_blank_but_keeps_width(self):
        out = pixelfont.text("AéB", 0, 0, 1)
        self.assertEqual(out.count("<use"), 2)
        self.assertEqual(pixelfont.text_width("AéB", 1), 17)


class StatsTest(unittest.TestCase):
    def test_level(self):
        self.assertEqual(gen.level_info(0), (0, 0, 10))
        self.assertEqual(gen.level_info(1284), (11, 74, 230))

    def test_streak_skips_empty_today(self):
        days = [day("2026-10-26", 4), day("2026-10-27", 1), day("2026-10-28", 3), day("2026-10-29", 0)]
        self.assertEqual(gen.streak(days, date(2026, 10, 29)), 3)

    def test_streak_counts_today_and_stops_at_gap(self):
        days = [day("2026-10-26", 4), day("2026-10-27", 0), day("2026-10-28", 3), day("2026-10-29", 1)]
        self.assertEqual(gen.streak(days, date(2026, 10, 29)), 2)

    def test_top_languages(self):
        repos = FAKE_RESPONSE["data"]["user"]["repositories"]["nodes"]
        self.assertEqual(gen.top_languages(repos, 4), [("Python", 80.0), ("TypeScript", 20.0)])

    def test_parse_stats(self):
        s = gen.parse_stats(FAKE_RESPONSE, date(2026, 10, 29))
        self.assertEqual((s["xp"], s["level"], s["streak"], s["repos"]), (1284, 11, 2, 31))


class RenderTest(unittest.TestCase):
    stats = gen.parse_stats(FAKE_RESPONSE, date(2026, 10, 29))

    def assert_svg(self, svg, label):
        root = ET.fromstring(svg)
        self.assertIn(label.lower(), root.get("aria-label").lower())

    def test_header(self):
        self.assert_svg(gen.render_header(self.stats), "EKO")

    def test_card(self):
        self.assert_svg(gen.render_card(self.stats, "2026-10-29 08:47 UTC"), "Level 11")

    def test_projects_and_buttons(self):
        for i, p in enumerate(gen.PROJECTS):
            self.assert_svg(gen.render_project(p, i), p["name"])
        for b in gen.BUTTONS:
            self.assert_svg(gen.render_button(b), b["label"])


class MainTest(unittest.TestCase):
    def test_writes_assets_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            gen.main(Path(d), fetch=lambda: FAKE_RESPONSE)
            self.assertTrue((Path(d) / "card.svg").exists())
            self.assertEqual(json.loads((Path(d) / "stats.json").read_text())["xp"], 1284)

    def test_falls_back_to_cache_when_api_down(self):
        def down():
            raise URLError("down")

        with tempfile.TemporaryDirectory() as d:
            gen.main(Path(d), fetch=lambda: FAKE_RESPONSE)
            (Path(d) / "card.svg").unlink()
            with self.assertLogs(level="WARNING") as logs:
                gen.main(Path(d), fetch=down)
            self.assertTrue((Path(d) / "card.svg").exists())
            self.assertTrue(logs.records[0].getMessage().startswith("::warning::"))  # GitHub Actions annotation

    def test_api_down_without_cache_fails(self):
        def down():
            raise URLError("down")

        with tempfile.TemporaryDirectory() as d, self.assertRaises(URLError):
            gen.main(Path(d), fetch=down)


if __name__ == "__main__":
    unittest.main()
