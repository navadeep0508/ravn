import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

def apply_migration():
    try:
        # Read the migration SQL file
        with open('migrations/add_completed_at_to_quiz_attempts.sql', 'r') as f:
            sql = f.read()
        
        # Execute the SQL
        result = supabase.rpc('execute', {'query': sql}).execute()
        print("Migration applied successfully!")
        return True
    except Exception as e:
        print(f"Error applying migration: {str(e)}")
        return False

if __name__ == "__main__":
    apply_migration()
