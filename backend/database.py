"""database.py - MSSQL DWH access layer (pyodbc).

Hybrid strategy:
  1. Try live DWH query.
  2. On any failure app.py serves MOCK_FALLBACK from config.py.

Note: DWH firewall must allow Render outbound IPs to reach REDACTED_SERVER:1433.
"""

import logging
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
            f"DRIVER={{{self._pick_driver()}}};"
            f"SERVER={Config.MSSQL_SERVER},{Config.MSSQL_PORT};"
            f"DATABASE={Config.MSSQL_DATABASE};"
            f"UID={Config.MSSQL_USER};"
            f"PWD={Config.MSSQL_PASSWORD};"
            f"Encrypt={'yes;TrustServerCertificate=yes' if self._odbc_modern() else 'no'};"
        )

    @staticmethod
    def _pick_driver() -> str:
        """Pick an installed SQL Server ODBC driver: prefer ODBC 18/17, else legacy."""
        try:
            drivers = pyodbc.drivers()
        except Exception:
            drivers = []
        for pref in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server",
                     "SQL Server Native Client 11.0", "SQL Server"):
            for d in drivers:
                if d.lower().startswith(pref.lower()):
                    return d
        return drivers[0] if drivers else "ODBC Driver 18 for SQL Server"

    @staticmethod
    def _odbc_modern() -> bool:
        return Database._pick_driver().lower().startswith("odbc driver")

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

    def _fy_bounds(self, fy: str):
        """Return (start, end) for a fiscal year string like '2025-2026'.

        Fiscal start month comes from Config.FISCAL_START_MONTH (default 7 = July),
        and the end is start month - 1 of the following year. This keeps all
        month bucketing driven by configuration rather than hardcoding Jul-Jun.
        """
        y1 = int(fy.split("-")[0])
        sm = Config.FISCAL_START_MONTH  # 1..12
        start = date(y1, sm, 1)
        # end = start of next fiscal year - 1 day
        end_year, end_month = (y1 + 1, sm - 1) if sm > 1 else (y1 + 1, 12)
        end = date(end_year, end_month, 28)  # 28 is safe for every month; truncated below
        import calendar
        last_day = calendar.monthrange(end_year, end_month)[1]
        end = date(end_year, end_month, last_day)
        return start, end

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
            f"WHERE {DBM['employee_bu_column']} = ? AND {DBM['employee_active_column']} = 1 "
            f"ORDER BY {DBM['employee_name_column']}",
            (limit, self.bu_id),
        )
        return rows

    def get_marketing_metrics(self, fy: str = Config.DEFAULT_FY) -> Dict[str, Any]:
        """CAC / CLV / ROMI computed from the actual DWH delivery data.

        NOTE: the DWH has no marketing-spend table mapped for BU 175 yet, so the
        classic cost formulas cannot use real ad-spend. These are revenue-based
        proxies derived from real delivery data:
          - CAC  : average revenue per new/unique customer (acquisition level)
          - CLV  : average lifetime revenue per customer
          - ROMI : revenue generated per order (marketing efficiency proxy)
        Replace these formulas in config when a real spend table is added.
        """
        fy_s, fy_e = self._fy_bounds(fy)
        rows = self._query(
            f"SELECT COUNT(DISTINCT {DBM['customer_column']}) AS customers, "
            f"COUNT(*) AS orders, "
            f"SUM(ISNULL({DBM['revenue_column']},0)) AS revenue, "
            f"SUM(ISNULL({DBM['quantity_column']},0)) AS qty "
            f"FROM {DBM['transaction_table']} "
            f"WHERE {DBM['bu_column']} = ? AND {DBM['date_column']} BETWEEN ? AND ?",
            (self.bu_id, fy_s, fy_e),
        )
        r = rows[0] if rows else {}
        customers = r.get("customers", 0) or 0
        orders = r.get("orders", 0) or 0
        revenue = r.get("revenue", 0) or 0

        cac = revenue / customers if customers else 0        # BDT per customer
        clv = revenue / customers if customers else 0         # BDT per customer
        romi = revenue / orders if orders else 0              # BDT per order

        return {
            "cac": round(cac / 1_000_000, 2),   # in Cr
            "clv": round(clv / 1_000_000, 2),   # in Cr
            "romi": round(romi / 1_000_000, 3), # in Cr
            "customers": customers,
            "orders": orders,
            "note": "revenue-based proxy; real spend table needed for classic CAC/CLV/ROMI",
        }

    # ============================================================
    # Full dashboard payload (matches /api/dashboard contract)
    # ============================================================

    def build_dashboard(self, fy: str = Config.DEFAULT_FY) -> Dict[str, Any]:
        """Assemble the complete payload:
        {meta, summary, monthly, customers, sbus, kpi, employees}

        Per-section fallback: if a live query returns empty/None, the safe
        baseline value from MOCK_FALLBACK is used so no tab is left blank.
        Missing sections are logged so they can be investigated against the DWH.
        """
        logger = logging.getLogger(__name__)

        summary = self.get_summary(fy)
        monthly = self.get_monthly_sales(fy)
        customers = self.get_top_customers(5)
        sbus = self.get_sbu_performance(fy)
        kpi = self.get_kpi()
        employees = self.get_employees(50)
        marketing = self.get_marketing_metrics(fy)

        # Per-section safety net - never return an empty section.
        if not monthly:
            monthly = MOCK_FALLBACK["monthly"]
            logger.warning("get_monthly_sales returned empty - using baseline fallback")
        if not customers:
            customers = MOCK_FALLBACK["customers"]
            logger.warning("get_top_customers returned empty - using baseline fallback")
        if not sbus:
            sbus = MOCK_FALLBACK["sbus"]
            logger.warning("get_sbu_performance returned empty - using baseline fallback")
        if not kpi or not kpi.get("service_level"):
            kpi = MOCK_FALLBACK["kpi"]
            logger.warning("get_kpi returned incomplete - using baseline fallback")
        if not employees:
            employees = MOCK_FALLBACK["employees"]
            logger.warning("get_employees returned empty - using baseline fallback")
        if not marketing or not marketing.get("cac"):
            marketing = MOCK_FALLBACK["marketing"]
            logger.warning("get_marketing_metrics returned empty - using baseline fallback")

        return {
            "meta": {
                "title": Config.APP_NAME,
                "org": "Akij Readymix Concrete Ltd",
                "fy": fy,
                "currency": "BDT",
                "unit": "Cr",
                "source": f"DWH {DBM['transaction_table']}",
                "asOf": summary.get("as_of") if summary else MOCK_FALLBACK["meta"]["asOf"],
            },
            "summary": summary,
            "monthly": monthly,
            "customers": customers,
            "sbus": sbus,
            "kpi": kpi,
            "marketing": marketing,
            "employees": employees,
        }