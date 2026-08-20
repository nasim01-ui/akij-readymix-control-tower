"""app.py - Flask REST API for Akij Readymix Control Tower.

Endpoints:
  GET /api/health            -> liveness
  GET /api/dashboard         -> {meta, summary, monthly, customers, sbus, kpi, employees}
  GET /api/debug             -> env var presence check (no secrets)
"""

import logging
import os
import traceback

from flask import Flask, jsonify
from flask_cors import CORS

from config import Config, MOCK_FALLBACK
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}})

db = Database()


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
    """Return {meta, summary, monthly, customers, sbus, kpi, employees}.
    Falls back to cached figures on DWH failure."""
    fy = Config.DEFAULT_FY
    try:
        payload = db.build_dashboard(fy)
        payload["meta"]["live"] = True
        return jsonify(payload)
    except Exception as e:
        logger.warning("DWH unavailable, serving fallback: %s", e)
        fallback = dict(MOCK_FALLBACK)
        fallback["meta"] = dict(MOCK_FALLBACK["meta"])
        fallback["meta"]["live"] = False
        fallback["meta"]["error"] = str(e)
        return jsonify(fallback)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)