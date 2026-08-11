import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database connection parameters from environment variables
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = os.getenv("POSTGRES_DB")

def drop_clinical_cases_table():
    # Connect to the virtual_patient database
    conn = psycopg2.connect(
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )
    cur = conn.cursor()
    
    # Drop the clinical_cases table
    cur.execute("DROP TABLE IF EXISTS clinical_cases CASCADE;")
    
    conn.commit()
    cur.close()
    conn.close()
    print("Clinical cases table dropped successfully!")

if __name__ == "__main__":
    print("Dropping clinical_cases table...")
    drop_clinical_cases_table()
    print("Table dropped.") 