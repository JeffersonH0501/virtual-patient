#!/usr/bin/env python3
"""
Simple test script to verify Azure OpenAI connection and environment variables.
"""

import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_openai import AzureOpenAIEmbeddings

def test_environment_variables():
    """Test if all required environment variables are set."""
    print("🔍 Testing Environment Variables...")
    
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT", 
        "AZURE_OPENAI_DEPLOYMENT_NAME",
        "AZURE_EMBEDDING_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION"
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {'*' * min(len(value), 8)}... (length: {len(value)})")
        else:
            print(f"❌ {var}: NOT SET")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n❌ Missing environment variables: {missing_vars}")
        return False
    
    print("\n✅ All environment variables are set!")
    return True

def test_azure_openai_llm():
    """Test Azure OpenAI LLM connection."""
    print("\n🤖 Testing Azure OpenAI LLM Connection...")
    
    try:
        llm = init_chat_model(
            "azure_openai:gpt-4o-mini",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION")
        )
        
        # Test with a simple message
        response = llm.invoke("Say 'Hello from Azure OpenAI!' in one sentence.")
        print(f"✅ LLM Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return False

def test_azure_openai_embeddings():
    """Test Azure OpenAI embeddings connection."""
    print("\n🔤 Testing Azure OpenAI Embeddings Connection...")
    
    try:
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=os.getenv("AZURE_EMBEDDING_DEPLOYMENT"),
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY")
        )
        
        # Test with a simple text
        test_text = "Hello, this is a test for embeddings."
        embedding = embeddings.embed_query(test_text)
        
        print(f"✅ Embedding generated successfully!")
        print(f"   Text: '{test_text}'")
        print(f"   Embedding dimensions: {len(embedding)}")
        print(f"   First few values: {embedding[:5]}")
        return True
        
    except Exception as e:
        print(f"❌ Embeddings Error: {e}")
        return False

def test_database_connection():
    """Test database connection."""
    print("\n🗄️ Testing Database Connection...")
    
    try:
        from app.core.database import SQLALCHEMY_DATABASE_URL
        print(f"✅ Database URL configured: {SQLALCHEMY_DATABASE_URL.split('@')[1] if '@' in SQLALCHEMY_DATABASE_URL else '***'}")
        
        # Test actual connection
        from sqlalchemy import create_engine, text
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful!")
        return True
        
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Azure OpenAI Connection Test")
    print("=" * 50)
    
    # Load environment variables
    load_dotenv()
    
    # Run tests
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Database Connection", test_database_connection),
        ("Azure OpenAI LLM", test_azure_openai_llm),
        ("Azure OpenAI Embeddings", test_azure_openai_embeddings),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Your Azure OpenAI setup is working correctly.")
        print("   You can now run: python -m app.agents.virtual_patient_agent")
    else:
        print("⚠️  Some tests failed. Please check your configuration.")

if __name__ == "__main__":
    main() 