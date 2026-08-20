"""database.py - MSSQL DWH access layer (pyodbc).

Hybrid strategy:
  1. Try live DWH query.
  2. On any failure app.py serves MOCK_FALLBACK from config.py.

Note: DWH firewall must allow Render outbound IPs to reach REDACTED_SERVER:1433.
"""

import os
from datetime import date
from typing import List, Dict, Any

import pyodbc

from config import Config, TABLE_MAP, MOCK_FALLBACK

TM = TABLE_MAP  # shorthand


class Database:
    """Typed query builders against TABLE_MAP schema."""

    def __init__(self):
        self.bu_id = Config.MSSQL_BU_ID

    # ---------------- connection ----------------
    def _conn_str(self) -> str:
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={Config.MSSQL_SERVER},{Config.MSSQL_PORT};"
            f"DATABASE={Config.MSSQL_DATABASE};"
            f"UID={Config.MSSQL_USER};"
            f"PWD={Config.MSSQL_PASSWORD};"
            f"Encrypt=yes;TrustServerCertificate=yes;"
        )

    def _connect(self):
        return pyodbc.connect(self._conn_str(), timeout=30)

    def _query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Run SELECT, return list of dicts."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    # ---------------- helpers ----------------
    @staticmethod
    def _cr(value) -> float:
        """BDT -> BDT Crore (1 Cr = 1e7)."""
        try:
            return round(float(value or 0) / 10_000_000, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _fy_bounds(fy: str):
        y1 = int(fy.split("-")[0])
        return date(y1, 7, 1), date(y1 + 1, 6, 30)

    # ============================================================
    # Query templates (all read from TABLE_MAP)
    # ============================================================

    def get_summary(self, fy: str = Config.DEFAULT_FY):
        """1. Revenue summary -> mtd / ytd / ann."""
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT MAX({TM['date_column']}) AS max_date "
            f"FROM {TM['transaction_table']} "
            f"WHERE {TM['bu_column']} = ?",
            (self.bu_id,),
        )
        if not rows or not rows[0]["max_date"]:
            return {"mtd": 0, "ytd": 0, "ann": 0, "as_of": None}

        max_d = rows[0]["max_date"]
        mtd_s = date(max_d.year, max_d.month, 1)

        def _sum(d1, d2):
            r = self._query(
                f"SELECT SUM(ISNULL({TM['revenue_column']},0)) AS rev, "
                f"SUM(ISNULL({TM['quantity_column']},0)) AS qty "
                f"FROM {TM['transaction_table']} "
                f"WHERE {TM['bu_column']} = ? AND {TM['date_column']} BETWEEN ? AND ?",
                (self.bu_id, d1, d2),
            )
            row = r[0] if r else {}
            return (row.get("rev", 0) or 0), (row.get("qty", 0) or 0)

        m_r, m_q = _sum(mtd_s, max_d)
        y_r, y_q = _sum(fy_s, max_d)
        a_r, a_q = _sum(fy_s, fy_e)

        return {
            "mtd": self._cr(m_r), "mtd_qty": m_q,
            "ytd": self._cr(y_r), "ytd_qty": y_q,
            "ann": self._cr(a_r), "ann_qty": a_q,
            "as_of": max_d.isoformat(),
        }

    def get_monthly(self, fy: str = Config.DEFAULT_FY):
        """2. Monthly revenue trend."""
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT MONTH({TM['date_column']}) AS m, YEAR({TM['date_column']}) AS y, "
            f"SUM(ISNULL({TM['revenue_column']},0)) AS rev, "
            f"SUM(ISNULL({TM['quantity_column']},0)) AS qty, "
            f"COUNT({TM['order_count_column']}) AS ord "
            f"FROM {TM['transaction_table']} "
            f"WHERE {TM['bu_column']} = ? AND {TM['date_column']} BETWEEN ? AND ? "
            f"GROUP BY MONTH({TM['date_column']}), YEAR({TM['date_column']}) "
            f"ORDER BY YEAR({TM['date_column']}), MONTH({TM['date_column']})",
            (self.bu_id, fy_s, fy_e),
        )
        names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        return [
            {"label": f"{names[r['m']-1]} {r['y']}", "revA": self._cr(r["rev"]),
             "quantity": r["qty"], "orders": r["ord"]}
            for r in rows
        ]

    def get_customers(self, limit: int = 5):
        """3. Top customers."""
        rows = self._query(
            f"SELECT TOP ? {TM['customer_name_column']} AS customer, "
            f"SUM(ISNULL({TM['revenue_column']},0)) AS rev, "
            f"SUM(ISNULL({TM['quantity_column']},0)) AS qty, "
            f"COUNT({TM['order_count_column']}) AS ord "
            f"FROM {TM['transaction_table']} "
            f"WHERE {TM['bu_column']} = ? "
            f"GROUP BY {TM['customer_name_column']} "
            f"ORDER BY rev DESC",
            (limit, self.bu_id),
        )
        return [
            {"customer": r["customer"], "revenue_cr": self._cr(r["rev"]),
             "quantity": r["qty"], "orders": r["ord"]}
            for r in rows
        ]

    def get_sbus(self, fy: str = Config.DEFAULT_FY):
        """4. SBU / zone performance."""
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT {TM['sbu_code_column']} AS code, {TM['sbu_name_column']} AS name, "
            f"SUM(ISNULL({TM['revenue_column']},0)) AS rev, "
            f"SUM(ISNULL({TM['quantity_column']},0)) AS qty "
            f"FROM {TM['transaction_table']} "
            f"WHERE {TM['bu_column']} = ? AND {TM['date_column']} BETWEEN ? AND ? "
            f"GROUP BY {TM['sbu_code_column']}, {TM['sbu_name_column']} "
            f"ORDER BY rev DESC",
            (self.bu_id, fy_s, fy_e),
        )
        return [
            {"code": r["code"], "name": r["name"],
             "revA": self._cr(r["rev"]), "quantity": r["qty"]}
            for r in rows
        ]

    def get_employees(self, limit: int = 100):
        """5. Employee / action table."""
        rows = self._query(
            f"SELECT TOP ? {TM['employee_id_column']} AS id, {TM['employee_name_column']} AS name, "
            f"{TM['employee_enroll_column']} AS enroll, {TM['employee_code_column']} AS code, "
            f"{TM['employee_designation_column']} AS designation "
            f"FROM {TM['employee_table']} "
            f"WHERE intBusinessUnitId = ? AND {TM['employee_active_column']} = 1 "
            f"ORDER BY {TM['employee_name_column']}",
            (limit, self.bu_id),
        )
        return rows

    def get_kpi(self):
        """6. KPI metrics (overall volumes + standard SLA placeholders)."""
        rows = self._query(
            f"SELECT COUNT({TM['order_count_column']}) AS total_orders, "
            f"SUM(ISNULL({TM['revenue_column']},0)) AS total_revenue, "
            f"SUM(ISNULL({TM['quantity_column']},0)) AS total_qty "
            f"FROM {TM['transaction_table']} "
            f"WHERE {TM['bu_column']} = ?",
            (self.bu_id,),
        )
        row = rows[0] if rows else {}
        return {
            "service_level": 95,
            "order_accuracy": 93,
            "fill_rate": 91,
            "total_orders": row.get("total_orders", 0) or 0,
            "total_revenue_cr": self._cr(row.get("total_revenue", 0)),
            "total_qty": row.get("total_qty", 0) or 0,
        }

    # ============================================================
    # Full dashboard payload
    # ============================================================

    def build_dashboard(self, fy: str = Config.DEFAULT_FY) -> Dict[str, Any]:
        """Assemble the complete window.TOWER payload."""
        summary = self.get_summary(fy)
        sbu_rows = self.get_sbus(fy)
        return {
            "meta": {
                "title": Config.APP_NAME,
                "org": "Akij Readymix Concrete Ltd",
                "fy": fy,
                "currency": "BDT",
                "unit": "Cr",
                "source": f"DWH {TM['transaction_table']}",
                "asOf": summary.get("as_of"),
            },
            "group": {
                "mtd": {"revA": summary.get("mtd", 0), "npA": 0,
                        "revB": summary.get("mtd", 0), "npB": 0},
                "ytd": {"revA": summary.get("ytd", 0), "npA": 0,
                        "revB": summary.get("ytd", 0), "npB": 0},
                "ann": {"revA": summary.get("ann", 0), "npA": 0,
                        "revB": summary.get("ann", 0), "npB": 0},
            },
            "months": self.get_monthly(fy),
            "days": {},
            "sbus": sbu_rows,
            "portfolio": {
                "clusters": [
                    {"key": "A", "label": "Premium", "count": 2, "revCr": 270},
                    {"key": "B", "label": "Standard", "count": 1, "revCr": 80},
                    {"key": "C", "label": "Value", "count": 1, "revCr": 15},
                ],
                "totalSBUs": len(sbu_rows),
                "trendLabels": ["Growing", "Stable", "Consolidating"],
            },
            "benchmarks": MOCK_FALLBACK["benchmarks"],
            "customers": self.get_customers(5),
            "kpi": self.get_kpi(),
            "employees": self.get_employees(50),
        }