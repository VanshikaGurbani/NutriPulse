"""Local MOCK of the CalorieNinjas and USDA endpoints, for UI screenshots and interaction counting only.

Data here is made up for layout testing. Never use anything measured through this server as an accuracy or
latency result.

    python tools/ux/mock_api.py 8765
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CN_ITEMS = {
    "rice": {"name": "white rice", "serving_size_g": 200.0, "calories": 260.0, "protein_g": 5.4, "carbohydrates_total_g": 57.0,
             "fat_total_g": 0.6, "fiber_g": 0.8, "sugar_g": 0.1, "sodium_mg": 2},
    "carrot": {"name": "carrots", "serving_size_g": 216.0, "calories": 88.0, "protein_g": 2.0, "carbohydrates_total_g": 20.9,
               "fat_total_g": 0.5, "fiber_g": 6.0, "sugar_g": 9.5, "sodium_mg": 150},
    "oat": {"name": "oatmeal", "serving_size_g": 100.0, "calories": 71.0, "protein_g": 2.5, "carbohydrates_total_g": 12.0,
            "fat_total_g": 1.5, "fiber_g": 1.7, "sugar_g": 0.3, "sodium_mg": 4},
}


def usda_foods(query):
    base = query.title()
    nut = lambda kcal: [{"nutrientId": 1008, "value": kcal}, {"nutrientId": 1003, "value": 3.0},  # noqa: E731
                        {"nutrientId": 1004, "value": 1.2}, {"nutrientId": 1005, "value": 20.0}, {"nutrientId": 1079, "value": 1.8}]
    return [
        {"fdcId": 1001, "description": f"{base}, cooked", "dataType": "SR Legacy", "foodNutrients": nut(120)},
        {"fdcId": 1002, "description": f"Bread, {query}", "dataType": "Survey (FNDDS)", "foodNutrients": nut(270)},
        {"fdcId": 1003, "description": f"{base}, raw", "dataType": "Foundation", "foodNutrients": nut(95)},
        {"fdcId": 1004, "description": f"Soup, {query}, canned", "dataType": "SR Legacy", "foodNutrients": nut(45)},
        {"fdcId": 1005, "description": f"{base}, dry", "dataType": "SR Legacy", "foodNutrients": nut(360)},
    ]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query).get("query", [""])[0].lower()
        if u.path.endswith("/foods/search"):
            return self._send({"foods": usda_foods(q or "food")})
        if "/food/" in u.path:
            gw = lambda g, m: {"amount": 1.0, "gramWeight": g, "modifier": m, "measureUnit": {"name": "undetermined"}}  # noqa: E731
            return self._send({"foodPortions": [gw(118.0, "medium"), gw(136.0, "large"), gw(174.0, "cup")]})
        if u.path.endswith("/nutrition"):
            items = [v for k, v in CN_ITEMS.items() if k in q]
            if "nothing" in q or not items:
                items = [] if "nothing" in q else [dict(CN_ITEMS["oat"], name=q or "food")]
            return self._send({"items": items})
        self._send({}, 404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
