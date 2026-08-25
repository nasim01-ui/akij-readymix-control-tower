"""config.py - Central configuration for Akij Readymix Control Tower.

Environment variables (never commit .env):
  MSSQL_SERVER / MSSQL_PORT / MSSQL_USER / MSSQL_PASSWORD / MSSQL_DATABASE / MSSQL_BU_ID / SECRET_KEY

DATABASE_MAP is the SINGLE source of truth for DWH table/column names.
All SQL in database.py reads ONLY from DATABASE_MAP - no hardcoded identifiers.

AKIJ ERP NOTE:
  The default mappings are the verified tables from the DWH INFORMATION_SCHEMA
  (sms.tblDeliveryHeaderArc, saas.empEmployeeBasicInfoArc,
   sms.tblEmployeeIncentiveArc).

  The specification mentions AKIJ ERP "tblISTransaction". That table was NOT
  verified/invented here. To point the app at tblISTransaction (once its real
  columns are confirmed), change ONLY the DATABASE_MAP values below - no code
  changes required. See the commented tblISTransaction placeholder.
"""

import os
from dotenv import load_dotenv
from typing import Dict, List

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

    # --- Fiscal calendar ---
    # Akij Readymix runs a Jul-Jun fiscal year. If the source uses a different
    # fiscal start, change FISCAL_START_MONTH (1-12). All month bucketing reads
    # this, so nothing else needs to change.
    FISCAL_START_MONTH = int(os.getenv("FISCAL_START_MONTH", "7"))  # July

    # Whether transaction_table."date_column" represents the POSTING date
    # (dteServerDate / dtePostingDate) vs a business/record date. This is a
    # documentation/config flag - adjust DATE_IS_POSTING_DATE to match the source.
    DATE_IS_POSTING_DATE = _env_bool("DATE_IS_POSTING_DATE", "true")


# ================================================================
# DATABASE_MAP - Single source of truth for DWH table/column names.
# These are the REAL tables verified from the DWH INFORMATION_SCHEMA.
# ================================================================
DATABASE_MAP = {
    # ------------------------------------------------------------------
    # Revenue / delivery transactions (verified schema).
    #
    # >>> AKIJ ERP tblISTransaction PLACEHOLDER <<<
    #   To use tblISTransaction once its real columns are confirmed, replace
    #   transaction_table and the *_column values below. For example (UNVERIFIED):
    #     "transaction_table": "dbo.tblISTransaction",
    #     "revenue_column": "numAmount",            # confirm sign/meaning
    #     "quantity_column": "numQuantity",
    #     "date_column": "dteTransactionDate",
    #     "bu_column": "intBusinessUnitId",
    #     "order_count_column": "intTransactionId",
    #     "customer_column": "strCustomerName",
    #   Only DATABASE_MAP edits needed - no code changes.
    # ------------------------------------------------------------------
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
    "employee_bu_column": "intBusinessUnitId",
    "employee_id_column": "intEmployeeBasicInfoId",
    "employee_name_column": "strEmployeeName",
    "employee_enroll_column": "strCardNumber",
    "employee_code_column": "strEmployeeCode",
    "employee_designation_column": "intDesignationId",  # FK id; name needs a join (not mapped yet)

    # Incentive / KPI source (verified schema)
    "incentive_table": "sms.tblEmployeeIncentiveArc",
    "employee_active_column": "isActive",
}

# Required keys that must exist in DATABASE_MAP at startup; validated in
# config.validate_database_map(). If validation fails the app aborts with a
# readable message instead of failing deep in a query.
REQUIRED_DATABASE_MAP_KEYS: List[str] = [
    "transaction_table",
    "revenue_column",
    "quantity_column",
    "date_column",
    "bu_column",
    "order_count_column",
    "customer_table",
    "customer_column",
    "sbu_code_column",
    "sbu_name_column",
    "employee_table",
    "employee_bu_column",
    "employee_id_column",
    "employee_name_column",
    "employee_enroll_column",
    "employee_code_column",
    "employee_designation_column",
    "employee_active_column",
]


def validate_database_map(map_: Dict[str, str] = None, required: List[str] = None) -> None:
    """Validate DATABASE_MAP has all required keys with non-empty values.

    Raises ValueError with a readable message listing every missing field.
    Called at app startup so config errors surface immediately.
    """
    m = map_ if map_ is not None else DATABASE_MAP
    req = required if required is not None else REQUIRED_DATABASE_MAP_KEYS
    missing = [k for k in req if not m.get(k)]
    if missing:
        raise ValueError(
            "DATABASE_MAP is missing required key(s): {0}. "
            "Add them to backend/config.py (see tblISTransaction placeholder).".format(
                ", ".join(missing)
            )
        )


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
        "mtd": 28.69, "ytd": 424.82, "ann": 365.47,
        "mtd_qty": 776751, "ytd_qty": 12903462, "ann_qty": 11300738,
        "as_of": "2026-08-23",
    },
    "monthly": [
        {"label": "Jul 2025", "revA": 35.70, "quantity": 1142012, "orders": 5292},
        {"label": "Aug 2025", "revA": 36.10, "quantity": 1160576, "orders": 5388},
        {"label": "Sep 2025", "revA": 32.09, "quantity": 1029688, "orders": 4805},
        {"label": "Oct 2025", "revA": 32.99, "quantity": 1064071, "orders": 4872},
        {"label": "Nov 2025", "revA": 31.64, "quantity": 1020698, "orders": 4585},
        {"label": "Dec 2025", "revA": 33.83, "quantity": 1075050, "orders": 4785},
        {"label": "Jan 2026", "revA": 37.00, "quantity": 1192187, "orders": 5280},
        {"label": "Feb 2026", "revA": 29.29, "quantity": 936129, "orders": 4209},
        {"label": "Mar 2026", "revA": 22.91, "quantity": 707757, "orders": 3120},
        {"label": "Apr 2026", "revA": 21.93, "quantity": 601562, "orders": 2643},
        {"label": "May 2026", "revA": 36.23, "quantity": 956611, "orders": 4186},
        {"label": "Jun 2026", "revA": 15.75, "quantity": 414397, "orders": 1899},
    ],
    "customers": [
        {"customer": "A One Polar Ltd (Unit-02)", "revenue_cr": 74.74, "quantity": 2484704, "orders": 11505},
        {"customer": "AKij Essentials Ltd.", "revenue_cr": 74.68, "quantity": 1901019, "orders": 9287},
        {"customer": "Rangs Properties", "revenue_cr": 43.22, "quantity": 1353558, "orders": 6010},
        {"customer": "Akij Textile Mills Ltd. (RMC)", "revenue_cr": 31.39, "quantity": 976097, "orders": 4279},
        {"customer": "Robintex (Bangladesh) Ltd.", "revenue_cr": 24.62, "quantity": 763347, "orders": 3615},
    ],
    "sbus": [
        {"code": "ARMCL", "name": "Akij Ready Mix Concrete Ltd", "revA": 365.47, "quantity": 11300738},
    ],
    "kpi": {"service_level": 95, "order_accuracy": 93, "fill_rate": 91,
            "total_orders": 238417, "total_revenue_cr": 1643.44, "total_qty": 52223928},
    "marketing": {
        "cac": 5.86,
        "clv": 5.86,
        "romi": 0.072,
        "customers": 624,
        "orders": 51064,
        "note": "real DWH revenue-proxy; live refresh 2026-08-23",
        "marketShare": {
            "national": "9.99%",
            "period": "Jul 2025 – Mar 2026",
            "totalMarketCft": 85050000,
            "akijCft": 8500000,
            "competitors": [
                {"name": "Shah Cement RMC", "share": 22.93, "cft": 19500000},
                {"name": "NDE", "share": 18.05, "cft": 15350000},
                {"name": "Bashundhora RMC", "share": 17.05, "cft": 14500000},
                {"name": "Crown RMC", "share": 16.46, "cft": 14000000},
                {"name": "Akij RMC", "share": 9.99, "cft": 8500000},
                {"name": "ABC RMC", "share": 6.70, "cft": 5700000},
                {"name": "Concord RMC", "share": 5.88, "cft": 5000000},
                {"name": "Mir RMC", "share": 2.94, "cft": 2500000},
            ],
            "trendLabels": ["Jan-25", "Feb-25", "Mar-25", "Apr-25", "May-25", "Jun-25", "Jul-25", "Aug-25", "Sep-25", "Oct-25", "Nov-25", "Dec-25", "Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26"],
            "trend": [13.45, 15.33, 13.80, 12.80, 13.16, 15.09, 14.59, 14.07, 13.10, 13.01, 11.47, 12.25, 12.30, 11.07, 9.63, 8.85, 10.79],
            "recent": [
                {"month": "May-26", "share": 9.59},
                {"month": "Jun-26", "share": 8.94},
                {"month": "Jul-26", "share": 10.02},
            ],
        },
    },
    "employees": [
        {"id": 562861, "name": "Md.Moniruzzaman", "enroll": "1359", "code": "ACRMC-1359", "designation": 1436},
        {"id": 562571, "name": "Rofiqul Islam", "enroll": "1321", "code": "ARMCL-1321", "designation": 1436},
    ],
}