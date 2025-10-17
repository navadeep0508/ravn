"""
Setup script to create .env file with Supabase credentials
Run this once to configure your environment
"""

import os

# Supabase credentials
SUPABASE_URL = "https://iqqqfccsguczlbymthfy.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlxcXFmY2NzZ3VjemxieW10aGZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjA0NjIzNjQsImV4cCI6MjA3NjAzODM2NH0.weI2fz5PZMnuRBVqKDaqG6MSvxjBqZgunWZPdUOampU"
SECRET_KEY = os.urandom(24).hex()

env_content = f"""SUPABASE_URL={SUPABASE_URL}
SUPABASE_KEY={SUPABASE_KEY}
SECRET_KEY={SECRET_KEY}
"""

# Write to .env file
with open('.env', 'w') as f:
    f.write(env_content)

print("✅ .env file created successfully!")
print("\nYour environment variables:")
print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_KEY: {SUPABASE_KEY[:20]}...")
print(f"SECRET_KEY: {SECRET_KEY[:20]}...")
print("\n⚠️  Keep your .env file secure and never commit it to version control!")
