"""Offline tests for the parsers, using samples shaped like the real pages."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobwatch  # noqa: E402

MOSTAQL_ROW = '''<tr class="project-row"> <td class="row-td"> <div class="card-title_wrapper"> <div class="card--title"> <h2 class="mrg--bt-reset"> <a href="https://mostaql.com/project/1291983-%D8%AA%D8%B7%D8%A8%D9%8A%D9%82" class="">تطبيق للمرتبطين - iOS + Android</a> </h2> <ul class="project__meta list-meta-items"> <li class="text-muted"> <i class="fa fa-user"></i> <bdi>Ali M.</bdi> </li> <li class="text-muted"> <time datetime="2026-11-10 14:16:01" title="x" itemprop="datePublished"> منذ 3 ساعات </time> </li> <li class="text-muted"> <span class="hsoub-file-signature-icon"></span> 17 عرض </li> </ul> </div> </div> <div class="mrg--tt"><p class="text-wrapper-div project__brief " ><a class="details-url" href="#">مطلوب تنفيذ تطبيق Flutter مع Widget</a></p></div> </td></tr>'''
MOSTAQL_SHOPIFY = MOSTAQL_ROW.replace("1291983", "1291976").replace("تطبيق للمرتبطين - iOS + Android", "متجر Shopify").replace("مطلوب تنفيذ تطبيق Flutter مع Widget", "تصميم متجر شوبيفاي")
MOSTAQL_CROWDED = MOSTAQL_ROW.replace("1291983", "1291111").replace("17 عرض", "65 عرض")

FREELANCER_JSON = {"status": "success", "result": {"projects": [
    {"id": 1, "title": "Flutter app for booking", "seo_url": "flutter/booking-1", "type": "fixed",
     "currency": {"code": "USD"}, "budget": {"minimum": 250, "maximum": 750},
     "bid_stats": {"bid_count": 12}, "time_submitted": 0, "preview_description": "Need Flutter dev",
     "jobs": [{"name": "Flutter"}]},
    {"id": 2, "title": "Unity game", "seo_url": "unity/game-2", "type": "fixed",
     "currency": {"code": "USD"}, "budget": {"minimum": 10, "maximum": 30},
     "bid_stats": {"bid_count": 5}, "time_submitted": 0, "preview_description": "Unity mobile app game",
     "jobs": [{"name": "Unity"}]},
]}}


class T(unittest.TestCase):
    def setUp(self):
        self.cfg = json.load(open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8"))

    def test_mostaql(self):
        page = "<table>" + MOSTAQL_ROW + MOSTAQL_SHOPIFY + MOSTAQL_CROWDED + "</table>"
        with mock.patch.object(jobwatch, "http_get", return_value=page):
            jobs = jobwatch.fetch_mostaql(self.cfg["mostaql"])
        self.assertEqual(list(jobs), ["mostaql:1291983"])
        j = jobs["mostaql:1291983"]
        self.assertEqual(j["url"], "https://mostaql.com/project/1291983-%D8%AA%D8%B7%D8%A8%D9%8A%D9%82")
        self.assertIn("17", j["bids"])

    def test_mostaql_blocked(self):
        with mock.patch.object(jobwatch, "http_get", return_value="<html>Just a moment...</html>"):
            with self.assertRaises(RuntimeError):
                jobwatch.fetch_mostaql(self.cfg["mostaql"])

    def test_freelancer(self):
        now = 1_800_000_000
        data = json.loads(json.dumps(FREELANCER_JSON))
        for p in data["result"]["projects"]:
            p["time_submitted"] = now - 600
        with mock.patch.object(jobwatch, "http_get", return_value=json.dumps(data)), \
                mock.patch.object(jobwatch.time, "time", return_value=now):
            jobs = jobwatch.fetch_freelancer(self.cfg["freelancer"])
        self.assertEqual(list(jobs), ["freelancer:1"])
        self.assertEqual(jobs["freelancer:1"]["url"], "https://www.freelancer.com/projects/flutter/booking-1")
        self.assertEqual(jobs["freelancer:1"]["budget"], "USD 250–750")

    def test_offer_count(self):
        self.assertEqual(jobwatch.offer_count("أضف أول عرض"), 0)
        self.assertEqual(jobwatch.offer_count("عرض واحد"), 1)
        self.assertEqual(jobwatch.offer_count("عرضان"), 2)
        self.assertEqual(jobwatch.offer_count("17 عرض"), 17)


if __name__ == "__main__":
    unittest.main()
