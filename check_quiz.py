import os
from dotenv import load_dotenv
from supabase import create_client

def check_quiz_data():
    load_dotenv()
    
    # Initialize Supabase client
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    supabase = create_client(supabase_url, supabase_key)
    
    # Get all quiz tasks
    result = supabase.table('tasks').select('*').eq('type', 'quiz').execute()
    
    print(f"Found {len(result.data)} quiz tasks:")
    for task in result.data:
        print(f"\nTask ID: {task['id']}")
        print(f"Title: {task.get('title')}")
        print(f"Has quiz_data: {bool(task.get('quiz_data'))}")
        print(f"quiz_data content: {task.get('quiz_data')}")
        
        # Try to parse the quiz data
        if task.get('quiz_data'):
            from app import parse_quiz_questions
            try:
                questions = parse_quiz_questions(task['quiz_data'])
                print(f"Successfully parsed {len(questions)} questions")
                for i, q in enumerate(questions, 1):
                    print(f"\nQuestion {i}:")
                    print(f"  Question: {q['question']}")
                    print(f"  Options: {q['options']}")
                    print(f"  Correct Answer: {q['correct_answer']}")
            except Exception as e:
                print(f"Error parsing quiz data: {str(e)}")

if __name__ == "__main__":
    check_quiz_data()
