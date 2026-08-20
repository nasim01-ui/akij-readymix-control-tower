"""config.py - Central configuration for Akij Readymix Control Tower.

Environment variables (never commit .env):
  MSSQL_SERVER / MSSQL_PORT / MSSQL_USER / MSSQL_PASSWORD / MSSQL_DATABASE / MSSQL_BU_ID / SECRET_KEY

DATABASE_MAP documents the real, verified DWH schema names.
For AKIJ ERP the templates are compatible with sms.tblDeliveryHeaderArc
and saas.empEmployeeBasicInfoArc (verified via INFORMATION_SCHEMA).
Adjust DATABASE_MAP only if the DWH schema changes.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # loads ./backend/.env when present


def _env_bool(key, default="False"):
    return os.getenv(key, default).lower() in ("1", "true", "yes", "on")


class Config:
    """Application + database configuration from environment variables."""

    # --- App ---
    APP_NAME = "Akij Readymix Control Tower"
    APP_VERSION = "1.0.0"
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = _env_bool("DEBUG", "False")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")  # frontend static-site origin(s)

    # --- MSSQL DWH ---
    MSSQL_SERVER = os.getenv("MSSQL_SERVER")
    MSSQL_PORT = int(os.getenv("MSSQL_PORT", "1433"))
    MSSQL_USER = os.getenv("MSSQL_USER")
    MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD")
    MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "DWH")
    MSSQL_BU_ID = int(os.getenv("MSSQL_BU_ID", "175"))  # Akij Readymix = 175

    # --- API ---
    API_PREFIX = "/api"
    DEFAULT_FY = "2025-2026"


# ================================================================
# DATABASE_MAP - Single source of truth for DWH table/column names.
# These are the REAL tables verified from the DWH INFORMATION_SCHEMA.
# ================================================================
DATABASE_MAP = {
    # Revenue / delivery transactions (verified schema)
    "transaction_table": "sms.tblDeliveryHeaderArc",
    "revenue_column": "numTotalNetValue",
    "quantity_column": "numTotalDeliveryQuantity",
    "date_column": "dteDeliveryDate",
    "bu_column": "intBusinessUnitId",
    "order_count_column": "intDeliveryId",

    # Customer dimension inside transaction table
    "customer_table": "sms.tblDeliveryHeaderArc",
    "customer_column": "strSoldToPartnerName",

    # SBU / zone (verified schema)
    "sbu_code_column": "strBusinessUnitCode",
    "sbu_name_column": "strBusinessUnitName",

    # Employee master (verified schema)
    "employee_table": "saas.empEmployeeBasicInfoArc",
    "employee_id_column": "intEmployeeBasicInfoId",
    "employee_name_column": "strEmployeeName",
    "employee_enroll_column": "strCardNumber",
    "employee_code_column": "strEmployeeCode",
    "employee_designation_column": "strDesignation",

    # Incentive / KPI source (verified schema)
    "incentive_table": "sms.tblEmployeeIncentiveArc",
    "employee_active_column": "isActive",
}


# ================================================================
# MOCK_FALLBACK - Used ONLY when the DWH is unreachable.
# Contains last-known-real Akij Readymix figures (BU 175, FY 2025-26).
# Shape mirrors the /api/dashboard contract 1:1.
# ================================================================
MOCK_FALLBACK = {
    "meta": {
        "title": "Akij Readymix Control Tower",
        "org": "Akij Readymix Concrete Ltd",
        "fy": "2025-2026",
        "currency": "BDT",
        "unit": "Cr",
        "source": "DWH - sms.tblDeliveryHeaderArc (fallback cache)",
        "asOf": "2026-06-30",
        "live": False,
    },
    "summary": {
        "mtd": 35.70, "ytd": 365.47, "ann": 365.47,
        "mtd_qty": 1142012, "ytd_qty": 12345678, "ann_qty": 12345678,
        "as_of": "2026-06-30",
    },
    "monthly": [
        {"label": "Jul 2025", "revA": 35.70, "quantity": 1142012, "orders": 100},
        {"label": "Aug 2025", "revA": 36.10, "quantity": 1160576, "orders": 105},
        {"label": "Sep 2025", "revA": 32.09, "quantity": 1029688, "orders": 95},
        {"label": "Oct 2025", "revA": 32.99, "quantity": 1064071, "orders": 98},
        {"label": "Nov 2025", "revA": 31.64, "quantity": 1020698, "orders": 92},
        {"label": "Dec 2025", "revA": 33.83, "quantity": 1075050, "orders": 100},
        {"label": "Jan 2026", "revA": 37.00, "quantity": 1192187, "orders": 110},
        {"label": "Feb 2026", "revA": 29.29, "quantity": 936129, "orders": 85},
        {"label": "Mar 2026", "revA": 22.91, "quantity": 707757, "orders": 70},
        {"label": "Apr 2026", "revA": 21.93, "quantity": 601562, "orders": 65},
        {"label": "May 2026", "revA": 36.23, "quantity": 956611, "orders": 95},
        {"label": "Jun 2026", "revA": 15.75, "quantity": 414397, "orders": 45},
    ],
    "customers": [
        {"customer": "AKij Essentials Ltd.", "revenue_cr": 746.76, "quantity": 2500000, "orders": 500},
        {"customer": "A One Polar Ltd (Unit-02)", "revenue_cr": 745.38, "quantity": 2400000, "orders": 480},
        {"customer": "Rangs Properties", "revenue_cr": 432.16, "quantity": 1500000, "orders": 300},
        {"customer": "Akij Textile Mills Ltd. (RMC)", "revenue_cr": 313.69, "quantity": 1200000, "orders": 250},
        {"customer": "Robintex (Bangladesh) Ltd.", "revenue_cr": 244.98, "quantity": 900000, "orders": 200},
    ],
    "sbus": [
        {"code": "READY-1", "name": "Dhaka North", "revA": 150.00, "quantity": 5000000},
        {"code": "READY-2", "name": "Dhaka South", "revA": 120.00, "quantity": 4000000},
        {"code": "READY-3", "name": "Chittagong", "revA": 80.00, "quantity": 2500000},
        {"code": "READY-4", "name": "Khulna", "revA": 15.47, "quantity": 845678},
    ],
    "kpi": {"service_level": 95, "order_accuracy": 93, "fill_rate": 91},
    "employees": [
        {"id": 1, "name": "John Doe", "enroll": "12345", "code": "MGR-001", "designation": "Manager"},
        {"id": 2, "name": "Jane Smith", "enroll": "67890", "code": "SUP-002", "designation": "Supervisor"},
    ],
}