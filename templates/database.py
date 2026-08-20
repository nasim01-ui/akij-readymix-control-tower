import pymssql
import os
from datetime import datetime, date
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.config = {
            'server': os.getenv('MSSQL_SERVER'),
            'port': int(os.getenv('MSSQL_PORT', 1433)),
            'user': os.getenv('MSSQL_USER'),
            'password': os.getenv('MSSQL_PASSWORD'),
            'database': os.getenv('MSSQL_DATABASE'),
        }
        self.bu_id = int(os.getenv('MSSQL_BU_ID', '175'))  # Akij Readymix = BU 175
    
    def _get_connection(self):
        """Create and return a database connection"""
        return pymssql.connect(**self.config)
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a query and return results as list of dicts"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        finally:
            conn.close()

    # ==================== REVENUE QUERIES ====================
    
    def get_revenue_summary(self) -> Dict:
        """Get MTD, YTD, Annual revenue summary"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            
            # Get latest date in data
            cursor.execute("""
                SELECT MAX(dteDeliveryDate) as max_date 
                FROM sms.tblDeliveryHeaderArc 
                WHERE intBusinessUnitId = %s
            """, (self.bu_id,))
            max_date_row = cursor.fetchone()
            if not max_date_row or not max_date_row['max_date']:
                return {"mtd": {}, "ytd": {}, "ann": {}}
            
            max_date = max_date_row['max_date']
            year = max_date.year
            month = max_date.month
            
            # FY starts July
            if month >= 7:
                fy_start = date(year, 7, 1)
                fy_end = date(year + 1, 6, 30)
            else:
                fy_start = date(year - 1, 7, 1)
                fy_end = date(year, 6, 30)
            
            # MTD
            mtd_start = date(max_date.year, max_date.month, 1)
            cursor.execute("""
                SELECT SUM(ISNULL(numTotalNetValue,0)) as revenue,
                       SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                AND dteDeliveryDate >= %s
                AND dteDeliveryDate <= %s
            """, (self.bu_id, mtd_start, max_date))
            mtd = cursor.fetchone() or {}
            
            # YTD
            cursor.execute("""
                SELECT SUM(ISNULL(numTotalNetValue,0)) as revenue,
                       SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                AND dteDeliveryDate >= %s
                AND dteDeliveryDate <= %s
            """, (self.bu_id, fy_start, max_date))
            ytd = cursor.fetchone() or {}
            
            # Annual (full FY)
            cursor.execute("""
                SELECT SUM(ISNULL(numTotalNetValue,0)) as revenue,
                       SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                AND dteDeliveryDate >= %s
                AND dteDeliveryDate <= %s
            """, (self.bu_id, fy_start, fy_end))
            ann = cursor.fetchone() or {}
            
            return {
                "mtd": self._to_cr(mtd.get('revenue', 0)),
                "ytd": self._to_cr(ytd.get('revenue', 0)),
                "ann": self._to_cr(ann.get('revenue', 0)),
                "mtd_qty": mtd.get('quantity', 0),
                "ytd_qty": ytd.get('quantity', 0),
                "ann_qty": ann.get('quantity', 0),
                "as_of": max_date.isoformat()
            }
        finally:
            conn.close()
    
    def get_monthly_revenue(self, fy: str) -> List[Dict]:
        """Get monthly revenue for a fiscal year"""
        if '-' in fy:
            year_start = int(fy.split('-')[0])
        else:
            year_start = int(fy)
        
        fy_start = date(year_start, 7, 1)
        fy_end = date(year_start + 1, 6, 30)
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("""
                SELECT 
                    MONTH(dteDeliveryDate) as month_num,
                    YEAR(dteDeliveryDate) as year_num,
                    SUM(ISNULL(numTotalNetValue,0)) as revenue,
                    SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity,
                    COUNT(*) as orders
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                AND dteDeliveryDate >= %s
                AND dteDeliveryDate <= %s
                GROUP BY MONTH(dteDeliveryDate), YEAR(dteDeliveryDate)
                ORDER BY YEAR(dteDeliveryDate), MONTH(dteDeliveryDate)
            """, (self.bu_id, fy_start, fy_end))
            
            rows = cursor.fetchall()
            month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
            
            result = []
            for row in rows:
                m = row['month_num']
                y = row['year_num']
                label = f"{month_names[m-1]} {y}"
                result.append({
                    "month": m,
                    "year": y,
                    "label": label,
                    "revenue_cr": self._to_cr(row['revenue']),
                    "quantity": row['quantity'],
                    "orders": row['orders']
                })
            return result
        finally:
            conn.close()
    
    def get_daily_revenue(self, start: str = None, end: str = None) -> List[Dict]:
        """Get daily revenue for a date range"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            
            query = """
                SELECT 
                    dteDeliveryDate,
                    SUM(ISNULL(numTotalNetValue,0)) as revenue,
                    SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity,
                    COUNT(*) as orders
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
            """
            params = [self.bu_id]
            
            if start:
                query += " AND dteDeliveryDate >= %s"
                params.append(start)
            if end:
                query += " AND dteDeliveryDate <= %s"
                params.append(end)
            
            query += " GROUP BY dteDeliveryDate ORDER BY dteDeliveryDate"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                "date": row['dteDeliveryDate'].isoformat() if row['dteDeliveryDate'] else None,
                "revenue_cr": self._to_cr(row['revenue']),
                "quantity": row['quantity'],
                "orders": row['orders']
            } for row in rows]
        finally:
            conn.close()
    
    def get_top_customers(self, limit: int = 10) -> List[Dict]:
        """Get top customers by revenue"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("""
                SELECT TOP %s
                    strSoldToPartnerName as customer,
                    SUM(ISNULL(numTotalNetValue,0)) as revenue,
                    SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity,
                    COUNT(*) as orders
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                GROUP BY strSoldToPartnerName
                ORDER BY revenue DESC
            """, (limit, self.bu_id))
            
            rows = cursor.fetchall()
            return [{
                "customer": row['customer'],
                "revenue_cr": self._to_cr(row['revenue']),
                "quantity": row['quantity'],
                "orders": row['orders']
            } for row in rows]
        finally:
            conn.close()
    
    def get_sbu_data(self) -> List[Dict]:
        """Get SBU/Zone data"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("""
                SELECT 
                    strBusinessUnitCode as code,
                    strBusinessUnitName as name,
                    SUM(ISNULL(numTotalNetValue,0)) as revenue,
                    SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                GROUP BY strBusinessUnitCode, strBusinessUnitName
                ORDER BY revenue DESC
            """, (self.bu_id,))
            
            rows = cursor.fetchall()
            return [{
                "code": row['code'],
                "name": row['name'],
                "revenue_cr": self._to_cr(row['revenue']),
                "quantity": row['quantity']
            } for row in rows]
        finally:
            conn.close()
    
    def get_portfolio_data(self) -> Dict:
        """Get portfolio/cluster data"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("""
                SELECT 
                    strBusinessUnitName as name,
                    SUM(ISNULL(numTotalNetValue,0)) as revenue,
                    SUM(ISNULL(numTotalDeliveryQuantity,0)) as quantity
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                GROUP BY strBusinessUnitName
                ORDER BY revenue DESC
            """, (self.bu_id,))
            
            rows = cursor.fetchall()
            clusters = []
            for i, row in enumerate(rows):
                clusters.append({
                    "key": chr(65 + i),  # A, B, C...
                    "label": row['name'],
                    "count": 1,
                    "revCr": self._to_cr(row['revenue']),
                    "sbus": []
                })
            
            return {
                "clusters": clusters,
                "totalSBUs": len(clusters),
                "trendLabels": ["Growing", "Stable", "Consolidating"]
            }
        finally:
            conn.close()
    
    def get_incentive_data(self, year: int = 2026) -> List[Dict]:
        """Get employee incentive data"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("""
                SELECT 
                    strEmployeeName,
                    strDesignation,
                    strTerritory,
                    intMonthId,
                    numTargetAmount,
                    numSalesAmount,
                    numAchievement,
                    numIncentiveAmount
                FROM sms.tblEmployeeIncentiveArc
                WHERE intBusinessUnitId = %s
                AND intYearId = %s
                AND isActive = 1
                ORDER BY strEmployeeName, intMonthId
            """, (self.bu_id, year))
            
            return cursor.fetchall()
        finally:
            conn.close()
    
    def get_employee_roster(self) -> List[Dict]:
        """Get employee roster for the BU"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("""
                SELECT 
                    intEmployeeBasicInfoId as id,
                    strEmployeeName as name,
                    strCardNumber as enroll,
                    strEmployeeCode as code,
                    strDesignation as designation
                FROM saas.empEmployeeBasicInfoArc
                WHERE intBusinessUnitId = %s
                AND isActive = 1
                ORDER BY strEmployeeName
            """, (self.bu_id,))
            
            return cursor.fetchall()
        finally:
            conn.close()
    
    def get_kpi_metrics(self) -> Dict:
        """Get key performance indicators"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            
            # Get latest date
            cursor.execute("""
                SELECT MAX(dteDeliveryDate) as max_date
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
            """, (self.bu_id,))
            max_date_row = cursor.fetchone()
            
            if not max_date_row or not max_date_row['max_date']:
                return {}
            
            max_date = max_date_row['max_date']
            
            # Calculate fill rate (placeholder - needs actual order data)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(ISNULL(numTotalNetValue,0)) as total_revenue,
                    SUM(ISNULL(numTotalDeliveryQuantity,0)) as total_qty
                FROM sms.tblDeliveryHeaderArc
                WHERE intBusinessUnitId = %s
                AND dteDeliveryDate >= DATEADD(month, -1, %s)
            """, (self.bu_id, max_date))
            
            row = cursor.fetchone() or {}
            
            return {
                "service_level": 95,
                "order_accuracy": 93,
                "fill_rate": 91,
                "total_orders": row.get('total_orders', 0),
                "total_revenue_cr": self._to_cr(row.get('total_revenue', 0)),
                "total_qty": row.get('total_qty', 0)
            }
        finally:
            conn.close()
    
    def _to_cr(self, value) -> float:
        """Convert BDT to Crore"""
        try:
            return round(float(value or 0) / 10_000_000, 2)
        except:
            return 0.0