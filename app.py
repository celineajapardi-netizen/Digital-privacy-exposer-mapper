"""
SHADOW web app: a tiny Flask server that serves the front-end and exposes the
engine as JSON.

    python app.py            then open http://127.0.0.1:5000

Routes
    GET  /                    the single-page app (static/index.html)
    GET  /api/catalogue       every kind of information, with its category
    POST /api/analyse         {"items": ["school", "city"]}  ->  full analysis
    GET  /api/scenarios       saved scenarios
    POST /api/scenarios       {"name": "...", "items": [...]}  ->  save one
    DELETE /api/scenarios/<id>

All analysis happens in the Python package; the browser only draws.
"""

from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory

from shadow import CATALOGUE, analyse
from shadow.catalogue import CATALOGUE_BY_KEY
from shadow.storage import ScenarioStore

app = Flask(__name__, static_folder="static", static_url_path="/static")
store = ScenarioStore()


def _items_from_request() -> list[str]:
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not isinstance(items, list) or any(k not in CATALOGUE_BY_KEY for k in items):
        raise ValueError("items must be a list of known catalogue keys")
    return items


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/catalogue")
def catalogue():
    return jsonify([info.__dict__ for info in CATALOGUE])


@app.post("/api/analyse")
def analyse_route():
    try:
        items = _items_from_request()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(analyse(items).to_dict())


@app.get("/api/scenarios")
def list_scenarios():
    return jsonify(store.list())


@app.post("/api/scenarios")
def save_scenario():
    try:
        items = _items_from_request()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    name = (request.get_json(silent=True) or {}).get("name", "")
    result = analyse(items, with_what_if=False)
    scenario_id = store.save(name, items, result.score, result.level)
    return jsonify(store.get(scenario_id)), 201


@app.delete("/api/scenarios/<int:scenario_id>")
def delete_scenario(scenario_id: int):
    if not store.delete(scenario_id):
        return jsonify({"error": "not found"}), 404
    return "", 204


if __name__ == "__main__":
    app.run(debug=True, port=5000)
