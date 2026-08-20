import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Flask configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Database
    MSSQL_SERVER = os.getenv('MSSQL_SERVER')
    MSSQL_PORT = int(os.getenv('MSSQL_PORT', 1433))
    MSSQL_USER = os.getenv('MSSQL_USER')
    MSSQL_PASSWORD = os.getenv('MSSQL_PASSWORD')
    MSSQL_DATABASE = os.getenv('MSSQL_DATABASE')
    MSSQL_BU_ID = os.getenv('MSSQL_BU_ID', '175')
    
    # App
    APP_NAME = 'Akij Readymix Control Tower'
    APP_VERSION = '1.0.0'
    
    # Cache
    CACHE_TIMEOUT = 300  # 5 minutes