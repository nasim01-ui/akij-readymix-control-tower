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

from config import Config, DATABASE_MAP, MOCK_FALLBACK

DBM = DATABASE_MAP  # shorthand


class Database:
    """Typed query builders against DATABASE_MAP schema."""

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
    # Query templates (all read from DATABASE_MAP)
    # ============================================================

    def get_summary(self, fy: str = Config.DEFAULT_FY):
        """Summary -> mtd / ytd / ann / quantities."""
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT MAX({DBM['date_column']}) AS max_date "
            f"FROM {DBM['transaction_table']} "
            f"WHERE {DBM['bu_column']} = ?",
            (self.bu_id,),
        )
        if not rows or not rows[0]["max_date"]:
            return {"mtd": 0, "ytd": 0, "ann": 0, "as_of": None}

        max_d = rows[0]["max_date"]
        mtd_s = date(max_d.year, max_d.month, 1)

        def _sum(d1, d2):
            r = self._query(
                f"SELECT SUM(ISNULL({DBM['revenue_column']},0)) AS rev, "
                f"SUM(ISNULL({DBM['quantity_column']},0)) AS qty "
                f"FROM {DBM['transaction_table']} "
                f"WHERE {DBM['bu_column']} = ? AND {DBM['date_column']} BETWEEN ? AND ?",
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

    def get_monthly_sales(self, fy: str = Config.DEFAULT_FY):
        """Monthly revenue trend."""
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT MONTH({DBM['date_column']}) AS m, YEAR({DBM['date_column']}) AS y, "
            f"SUM(ISNULL({DBM['revenue_column']},0)) AS rev, "
            f"SUM(ISNULL({DBM['quantity_column']},0)) AS qty, "
            f"COUNT({DBM['order_count_column']}) AS ord "
            f"FROM {DBM['transaction_table']} "
            f"WHERE {DBM['bu_column']} = ? AND {DBM['date_column']} BETWEEN ? AND ? "
            f"GROUP BY MONTH({DBM['date_column']}), YEAR({DBM['date_column']}) "
            f"ORDER BY YEAR({DBM['date_column']}), MONTH({DBM['date_column']})",
            (self.bu_id, fy_s, fy_e),
        )
        names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        return [
            {"label": f"{names[r['m']-1]} {r['y']}", "revA": self._cr(r["rev"]),
             "quantity": r["qty"], "orders": r["ord"]}
            for r in rows
        ]

    def get_top_customers(self, limit: int = 5):
        """Top customers by revenue."""
        rows = self._query(
            f"SELECT TOP ? {DBM['customer_column']} AS customer, "
            f"SUM(ISNULL({DBM['revenue_column']},0)) AS rev, "
            f"SUM(ISNULL({DBM['quantity_column']},0)) AS qty, "
            f"COUNT({DBM['order_count_column']}) AS ord "
            f"FROM {DBM['transaction_table']} "
            f"WHERE {DBM['bu_column']} = ? "
            f"GROUP BY {DBM['customer_column']} "
            f"ORDER BY rev DESC",
            (limit, self.bu_id),
        )
        return [
            {"customer": r["customer"], "revenue_cr": self._cr(r["rev"]),
             "quantity": r["qty"], "orders": r["ord"]}
            for r in rows
        ]

    def get_sbu_performance(self, fy: str = Config.DEFAULT_FY):
        """SBU / zone performance."""
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT {DBM['sbu_code_column']} AS code, {DBM['sbu_name_column']} AS name, "
            f"SUM(ISNULL({DBM['revenue_column']},0)) AS rev, "
            f"SUM(ISNULL({DBM['quantity_column']},0)) AS qty "
            f"FROM {DBM['transaction_table']} "
            f"WHERE {DBM['bu_column']} = ? AND {DBM['date_column']} BETWEEN ? AND ? "
            f"GROUP BY {DBM['sbu_code_column']}, {DBM['sbu_name_column']} "
            f"ORDER BY rev DESC",
            (self.bu_id, fy_s, fy_e),
        )
        return [
            {"code": r["code"], "name": r["name"],
             "revA": self._cr(r["rev"]), "quantity": r["qty"]}
            for r in rows
        ]

    def get_kpi(self):
        """KPI metrics (overall volumes + standard SLA placeholders)."""
        rows = self._query(
            f"SELECT COUNT({DBM['order_count_column']}) AS total_orders, "
            f"SUM(ISNULL({DBM['revenue_column']},0)) AS total_revenue, "
            f"SUM(ISNULL({DBM['quantity_column']},0)) AS total_qty "
            f"FROM {DBM['transaction_table']} "
            f"WHERE {DBM['bu_column']} = ?",
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

    def get_employees(self, limit: int = 100):
        """Employee / action table."""
        rows = self._query(
            f"SELECT TOP ? {DBM['employee_id_column']} AS id, {DBM['employee_name_column']} AS name, "
            f"{DBM['employee_enroll_column']} AS enroll, {DBM['employee_code_column']} AS code, "
            f"{DBM['employee_designation_column']} AS designation "
            f"FROM {DBM['employee_table']} "
            f"WHERE intBusinessUnitId = ? AND {DBM['employee_active_column']} = 1 "
            f"ORDER BY {DBM['employee_name_column']}",
            (limit, self.bu_id),
        )
        return rows

    # ============================================================
    # Full dashboard payload (matches /api/dashboard contract)
    # ============================================================

    def build_dashboard(self, fy: str = Config.DEFAULT_FY) -> Dict[str, Any]:
        """Assemble the complete payload:
        {meta, summary, monthly, customers, sbus, kpi, employees}
        """
        summary = self.get_summary(fy)
        return {
            "meta": {
                "title": Config.APP_NAME,
                "org": "Akij Readymix Concrete Ltd",
                "fy": fy,
                "currency": "BDT",
                "unit": "Cr",
                "source": f"DWH {DBM['transaction_table']}",
                "asOf": summary.get("as_of"),
            },
            "summary": summary,
            "monthly": self.get_monthly_sales(fy),
            "customers": self.get_top_customers(5),
            "sbus": self.get_sbu_performance(fy),
            "kpi": self.get_kpi(),
            "employees": self.get_employees(50),
        }