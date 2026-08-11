#!/usr/bin/env python3
"""
Script to initialize PostgresStore and set up procedural memory patterns.
This should be run once to create the shared procedural memory store that can be used across all interviews.
"""

import os
import sys
import traceback

from dotenv import load_dotenv
from psycopg import Connection
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from langchain.embeddings import init_embeddings
from datetime import datetime

# Load environment variables
load_dotenv()

# Get database connection parameters
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "virtual_patient")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Construct database URL
SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

def initialize_postgres_store():
    """Initialize PostgresStore and PostgresSaver"""
    try:
        print("🔧 Initializing PostgresStore and PostgresSaver...")
        
        # Initialize embeddings for the store
        embeddings = init_embeddings(
            "azure_openai:text-embedding-3-small",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION")
        )
        
        # Use Connection.connect like in the existing code
        with Connection.connect(SQLALCHEMY_DATABASE_URL, autocommit=True) as conn:
            # Initialize PostgresStore with index configuration (this will create store_vectors table)
            store = PostgresStore(
                conn=conn,
                index={
                    "dims": 1536,
                    "embed": embeddings,
                }
            )
            checkpointer = PostgresSaver(conn=conn)
            
            # Setup the store and checkpointer (this will create all required tables)
            store.setup()
            checkpointer.setup()
            
            print("✅ PostgresStore and PostgresSaver setup completed")
            return True
        
    except Exception as e:
        print(f"❌ Error initializing PostgresStore: {e}")
        print(f"🔍 Full error: {traceback.format_exc()}")
        return False

def setup_procedural_memory_patterns():
    """Set up the default procedural memory patterns in the shared namespace"""
    try:
        print("🧠 Setting up procedural memory patterns...")
        
        # Initialize embeddings
        embeddings = init_embeddings(
            "azure_openai:text-embedding-3-small",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION")
        )
        
        # Create PostgresStore with embeddings
        with PostgresStore.from_conn_string(
            SQLALCHEMY_DATABASE_URL,
            index={
                "dims": 1536,
                "embed": embeddings,
            }
        ) as store:
            
            # Define the shared namespace for procedural memory
            namespace = ("procedural_memory_store",)
            
            # Default procedural memory patterns
            default_patterns = [
                {
                    "trigger": "pain_assessment",
                    "pattern": "When asked about pain, describe location, duration, and what makes it better/worse",
                    "example": "The pain is in my head, been going on for a week, and it's worse in the mornings",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "medication_inquiry",
                    "pattern": "When asked about medications, mention current medications, dosages if known, and any side effects",
                    "example": "I take ibuprofen occasionally for the headaches, but I try not to take it too often",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "family_history",
                    "pattern": "When asked about family history, mention relevant conditions in immediate family members",
                    "example": "My mother has diabetes, and my father had high blood pressure",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "lifestyle_questions",
                    "pattern": "When asked about lifestyle, be honest about habits while showing some health awareness",
                    "example": "I know I should eat better and exercise more, but my schedule makes it challenging",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "symptom_details",
                    "pattern": "When asked for symptom details, provide specific information about timing, severity, and associated factors",
                    "example": "The pain started about 3 days ago, it's a sharp pain that comes and goes, and it's worse when I move my head",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "medical_history",
                    "pattern": "When asked about medical history, mention relevant past conditions, surgeries, and treatments",
                    "example": "I had my appendix removed when I was 20, and I've been treated for high blood pressure for the last 5 years",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "social_history",
                    "pattern": "When asked about social history, be honest about lifestyle factors like smoking, drinking, and occupation",
                    "example": "I work as a software engineer, I don't smoke, and I have a glass of wine with dinner occasionally",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                },
                {
                    "trigger": "allergy_inquiry",
                    "pattern": "When asked about allergies, mention any known allergies and reactions",
                    "example": "I'm allergic to penicillin - it gives me a rash. I also get hives from shellfish",
                    "created_at": datetime.now().isoformat(),
                    "usage_count": 0
                }
            ]
            
            # Store each pattern in the shared namespace
            for pattern in default_patterns:
                key = f"pattern_{pattern['trigger']}"
                store.put(namespace, key, pattern)
                print(f"  ✅ Stored pattern: {pattern['trigger']}")
            
            print(f"✅ Successfully stored {len(default_patterns)} procedural memory patterns")
            print(f"   Namespace: {namespace}")
            
            # Verify the patterns were stored
            print("\n🔍 Verifying stored patterns...")
            for pattern in default_patterns:
                key = f"pattern_{pattern['trigger']}"
                stored_pattern = store.get(namespace, key)
                if stored_pattern:
                    print(f"  ✅ Verified: {pattern['trigger']}")
                else:
                    print(f"  ❌ Failed to verify: {pattern['trigger']}")
                    return False
            
            return True
            
    except Exception as e:
        traceback.print_exc()
        print(f"❌ Error setting up procedural memory patterns: {e}")
        return False

def check_existing_patterns():
    """Check if procedural memory patterns already exist"""
    try:
        print("🔍 Checking for existing procedural memory patterns...")
        
        # Initialize embeddings
        embeddings = init_embeddings(
            "azure_openai:text-embedding-3-small",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION")
        )
        
        # Create PostgresStore with embeddings
        with PostgresStore.from_conn_string(
            SQLALCHEMY_DATABASE_URL,
            index={
                "dims": 1536,
                "embed": embeddings,
            }
        ) as store:
            
            namespace = ("procedural_memory_store",)
            
            # Check for existing patterns
            existing_patterns = []
            pattern_keys = [
                "pattern_pain_assessment",
                "pattern_medication_inquiry", 
                "pattern_family_history",
                "pattern_lifestyle_questions",
                "pattern_symptom_details",
                "pattern_medical_history",
                "pattern_social_history",
                "pattern_allergy_inquiry"
            ]
            
            for key in pattern_keys:
                pattern = store.get(namespace, key)
                if pattern:
                    existing_patterns.append(key)
            
            if existing_patterns:
                print(f"⚠️  Found {len(existing_patterns)} existing patterns:")
                for pattern in existing_patterns:
                    print(f"    - {pattern}")
                return True
            else:
                print("✅ No existing patterns found")
                return False
                
    except Exception as e:
        print(f"❌ Error checking existing patterns: {e}")
        return False

def main():
    """Main function to initialize procedural memory"""
    print("🚀 Initializing Procedural Memory System")
    print("=" * 50)
    
    # Step 1: Initialize PostgresStore
    if not initialize_postgres_store():
        print("❌ Failed to initialize PostgresStore")
        sys.exit(1)
    
    # Step 2: Check for existing patterns
    if check_existing_patterns():
        print("\n⚠️  Procedural memory patterns already exist.")
        response = input("Do you want to overwrite them? (y/N): ").strip().lower()
        if response != 'y':
            print("✅ Keeping existing patterns. Exiting.")
            sys.exit(0)
        else:
            print("🔄 Proceeding to overwrite existing patterns...")
    
    # Step 3: Set up procedural memory patterns
    if not setup_procedural_memory_patterns():
        print("❌ Failed to set up procedural memory patterns")
        sys.exit(1)
    
    print("\n🎉 Procedural Memory System initialization completed successfully!")
    print("   The procedural memory patterns are now available to all interviews.")
    print("   Namespace: ('procedural_memory_store',)")

if __name__ == "__main__":
    main()
