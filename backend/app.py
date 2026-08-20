"""app.py - Flask REST API for Akij Readymix Control Tower.

Endpoints:
  GET /api/health            -> liveness
  GET /api/dashboard         -> full window.TOWER payload
  GET /api/debug             -> env var presence check (no secrets)

Also serves the frontend from ../index.html (repo root) when hosted
by the same Render Web Service.
"""

import logging
import os
import traceback

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

from config import Config, MOCK_FALLBACK
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}})

db = Database()
FRONTEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root


# ---------------- Error handling ----------------
@app.errorhandler(500)
def internal_error(error):
    logger.error(traceback.format_exc())
    return jsonify({"error": "Internal Server Error"}), 500


# ---------------- API endpoints ----------------
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": Config.APP_NAME, "version": Config.APP_VERSION})


@app.route("/api/debug")
def debug():
    """Presence check only - NEVER return secret values."""
    return jsonify({
        "env": {k: ("SET" if os.getenv(k) else "MISSING")
                for k in ["MSSQL_SERVER", "MSSQL_PORT", "MSSQL_USER", "MSSQL_PASSWORD",
                          "MSSQL_DATABASE", "MSSQL_BU_ID", "SECRET_KEY"]},
        "pyodbc_available": True,
    })


@app.route("/api/dashboard")
def dashboard():
    """Full window.TOWER payload. Falls back to cached figures on DB failure."""
    fy = Config.DEFAULT_FY
    try:
        payload = db.build_dashboard(fy)
        payload["meta"]["live"] = True
        return jsonify(payload)
    except Exception as e:
        logger.warning("DWH unavailable, serving fallback: %s", e)
        fallback = dict(MOCK_FALLBACK)
        fallback["meta"]["live"] = False
        fallback["meta"]["error"] = str(e)
        return jsonify(fallback)


# ---------------- Frontend (optional same-host hosting) ----------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)