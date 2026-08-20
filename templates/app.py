from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os
from database import Database
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize database
db = Database()

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "service": "akij-readymix-control-tower"})

@app.route('/api/meta')
def get_meta():
    """Get metadata"""
    return jsonify({
        "title": "Akij Readymix Control Tower",
        "owner": "Readymix Team",
        "org": "Akij Readymix Concrete Ltd",
        "fy": "2025-2026",
        "currency": "BDT",
        "unit": "Cr",
        "source": "DWH - sms.tblDeliveryHeaderArc"
    })

@app.route('/api/revenue/summary')
def revenue_summary():
    """Get revenue summary (MTD, YTD, Annual)"""
    try:
        data = db.get_revenue_summary()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/revenue/monthly')
def revenue_monthly():
    """Get monthly revenue data"""
    try:
        fy = request.args.get('fy', '2025-2026')
        data = db.get_monthly_revenue(fy)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/revenue/daily')
def revenue_daily():
    """Get daily revenue data for a date range"""
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        data = db.get_daily_revenue(start, end)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/customers/top')
def top_customers():
    """Get top customers by revenue"""
    try:
        limit = request.args.get('limit', 10, type=int)
        data = db.get_top_customers(limit)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sbus')
def get_sbus():
    """Get SBU data"""
    try:
        data = db.get_sbu_data()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/portfolio')
def get_portfolio():
    """Get portfolio/cluster data"""
    try:
        data = db.get_portfolio_data()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/incentives')
def get_incentives():
    """Get employee incentive data"""
    try:
        year = request.args.get('year', 2026, type=int)
        data = db.get_incentive_data(year)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/employees')
def get_employees():
    """Get employee roster"""
    try:
        data = db.get_employee_roster()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/kpi')
def get_kpi():
    """Get KPI metrics"""
    try:
        data = db.get_kpi_metrics()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)