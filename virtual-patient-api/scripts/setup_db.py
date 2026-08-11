import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Get database connection parameters from environment variables
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

def create_database():
    # Connect to PostgreSQL server
    conn = psycopg2.connect(
        dbname='postgres',
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    
    # Create database if it doesn't exist
    cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{POSTGRES_DB}'")
    exists = cur.fetchone()
    if not exists:
        cur.execute(f'CREATE DATABASE {POSTGRES_DB}')
    
    cur.close()
    conn.close()

def drop_tables():
    # Connect to the virtual_patient database
    conn = psycopg2.connect(
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )
    cur = conn.cursor()
    
    # Drop all tables
    cur.execute("""
        DROP TABLE IF EXISTS personalities CASCADE;
        DROP TABLE IF EXISTS organizations CASCADE;
        DROP TABLE IF EXISTS clinical_cases CASCADE;
        DROP TABLE IF EXISTS medical_interviews CASCADE;
        DROP TABLE IF EXISTS interview_messages CASCADE;
        DROP TABLE IF EXISTS user_hypotheses CASCADE;
        DROP TABLE IF EXISTS session_notes CASCADE;
        DROP TABLE IF EXISTS progress_summaries CASCADE;
        DROP TABLE IF EXISTS teacher_feedback CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
    """)
    conn.commit()
    cur.close()
    conn.close()

def create_tables():
    # Connect to the virtual_patient database
    conn = psycopg2.connect(
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )
    cur = conn.cursor()
    
    # Create user_role enum type
    cur.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('teacher', 'student');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE,
            email VARCHAR(255) UNIQUE,
            full_name VARCHAR(255),
            hashed_password VARCHAR(255) NOT NULL,
            disabled BOOLEAN DEFAULT FALSE,
            preferred_language VARCHAR(50) DEFAULT 'en',
            role user_role NOT NULL DEFAULT 'student',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create organizations table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create case type enum
    cur.execute("""
        DO $$ BEGIN
            CREATE TYPE case_type AS ENUM ('default', 'custom');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create clinical_cases table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clinical_cases (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            case_type case_type NOT NULL DEFAULT 'default',
            organization_id INTEGER REFERENCES organizations(id),
            active BOOLEAN DEFAULT TRUE,
            icon VARCHAR(255),
            age INTEGER,
            weight_in_kg FLOAT,
            physical_requirements TEXT,
            socioeconomic_status TEXT,
            female_photo VARCHAR(255),
            male_photo VARCHAR(255),
            female_name VARCHAR(255),
            male_name VARCHAR(255),
            patient_context TEXT,
            chief_complaint TEXT,
            present_illness TEXT,
            personal_medical_history TEXT,
            surgical_history TEXT,
            family_history TEXT,
            medications TEXT,
            habits TEXT,
            allergies TEXT,
            concerns TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            title_translations JSONB DEFAULT '{}',
            description_translations JSONB DEFAULT '{}',
            chief_complaint_translations JSONB DEFAULT '{}',
            present_illness_translations JSONB DEFAULT '{}',
            personal_medical_history_translations JSONB DEFAULT '{}',
            surgical_history_translations JSONB DEFAULT '{}',
            family_history_translations JSONB DEFAULT '{}',
            medications_translations JSONB DEFAULT '{}',
            habits_translations JSONB DEFAULT '{}',
            allergies_translations JSONB DEFAULT '{}',
            concerns_translations JSONB DEFAULT '{}',
            physical_requirements_translations JSONB DEFAULT '{}',
            socioeconomic_status_translations JSONB DEFAULT '{}',
            patient_context_translations JSONB DEFAULT '{}',
            female_name_translations JSONB DEFAULT '{}',
            male_name_translations JSONB DEFAULT '{}'
        )
    """)
    
    # Create personalities table (must be created before medical_interviews)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS personalities (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            namespace_key VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            name_translations JSONB DEFAULT '{}'
        )
    """)
    
    # Create medical_interviews table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medical_interviews (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            clinical_case_id INTEGER REFERENCES clinical_cases(id) ON DELETE CASCADE NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP WITH TIME ZONE,
            total_duration INTEGER DEFAULT 0,
            interview_metadata JSONB,
            patient_name VARCHAR(255),
            patient_photo VARCHAR(255),
            patient_gender VARCHAR(50),
            personality_id INTEGER REFERENCES personalities(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create interview_messages table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS interview_messages (
            id SERIAL PRIMARY KEY,
            interview_id INTEGER REFERENCES medical_interviews(id) ON DELETE CASCADE,
            sender_type VARCHAR(20) NOT NULL CHECK (sender_type IN ('user', 'patient')),
            content TEXT NOT NULL,
            message_type VARCHAR(50) DEFAULT 'text',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            message_metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create user_hypotheses table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_hypotheses (
            id SERIAL PRIMARY KEY,
            interview_id INTEGER REFERENCES medical_interviews(id) ON DELETE CASCADE,
            hypothesis_text TEXT NOT NULL,
            hypothesis_order INTEGER NOT NULL CHECK (hypothesis_order >= 1 AND hypothesis_order <= 3),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(interview_id, hypothesis_order)
        )
    """)
    
    # Create session_notes table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_notes (
            id SERIAL PRIMARY KEY,
            interview_id INTEGER REFERENCES medical_interviews(id) ON DELETE CASCADE,
            notes_content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create progress_summaries table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS progress_summaries (
            id SERIAL PRIMARY KEY,
            medical_interview_id INTEGER REFERENCES medical_interviews(id) ON DELETE CASCADE UNIQUE,
            age INTEGER,
            current_symptoms JSONB,
            allergies JSONB,
            medications JSONB,
            diet_information TEXT,
            current_illnesses JSONB,
            family_history JSONB,
            summary_text TEXT,
            last_updated_message_id INTEGER REFERENCES interview_messages(id),
            update_count INTEGER DEFAULT 0,
            confidence_score FLOAT DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create interview_evaluations table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS interview_evaluations (
            id SERIAL PRIMARY KEY,
            medical_interview_id INTEGER REFERENCES medical_interviews(id) ON DELETE CASCADE UNIQUE,
            evaluation_results JSONB NOT NULL,
            overall_score INTEGER CHECK (overall_score >= 1 AND overall_score <= 10),
            completion_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create teacher_feedback table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teacher_feedback (
            id SERIAL PRIMARY KEY,
            feedback TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            medical_interview_id INTEGER REFERENCES medical_interviews(id) ON DELETE CASCADE,
            teacher_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    
    # Create indexes for better performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interview_messages_interview_id ON interview_messages(interview_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interview_messages_timestamp ON interview_messages(timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_hypotheses_interview_id ON user_hypotheses(interview_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_medical_interviews_user_id ON medical_interviews(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_medical_interviews_status ON medical_interviews(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_medical_interviews_personality_id ON medical_interviews(personality_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_progress_summaries_medical_interview_id ON progress_summaries(medical_interview_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interview_evaluations_medical_interview_id ON interview_evaluations(medical_interview_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_feedback_medical_interview_id ON teacher_feedback(medical_interview_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_feedback_teacher_id ON teacher_feedback(teacher_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_personalities_namespace_key ON personalities(namespace_key)")
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("Dropping tables...")
    drop_tables()
    print("Creating database...")
    create_database()
    print("Creating tables...")
    create_tables()
    print("Database setup completed!") 