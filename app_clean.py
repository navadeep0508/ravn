from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import random
import string
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client

def format_datetime(value, format='%b %d, %Y %I:%M %p'):
    """Format a datetime object or ISO format string to a readable format."""
    if value is None:
        return "Never"
    if isinstance(value, str):
        try:
            # Try parsing ISO format string
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return value  # Return as is if parsing fails
    try:
        return value.strftime(format)
    except (AttributeError, ValueError):
        return str(value)  # Fallback to string representation

def youtube_id_filter(url):
    """Extract YouTube video ID from various YouTube URL formats"""
    if not url:
        return None

    import re

    # Handle different YouTube URL formats
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def convert_to_youtube_embed(url):
    """Convert various YouTube URL formats to embed format"""
    if not url:
        return None

    import re

    # Handle different YouTube URL formats and convert to embed format
    patterns = [
        # youtu.be/VIDEO_ID -> youtube.com/embed/VIDEO_ID
        (r'https?://youtu\.be/([a-zA-Z0-9_-]{11})', r'https://www.youtube.com/embed/\1'),
        # youtube.com/watch?v=VIDEO_ID -> youtube.com/embed/VIDEO_ID
        (r'https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})', r'https://www.youtube.com/embed/\1'),
        # youtube.com/embed/VIDEO_ID (already embed format) -> keep as is
        (r'https?://(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})', r'https://www.youtube.com/embed/\1'),
        # youtube.com/v/VIDEO_ID -> youtube.com/embed/VIDEO_ID
        (r'https?://(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})', r'https://www.youtube.com/embed/\1'),
    ]

    for pattern, replacement in patterns:
        if re.search(pattern, url):
            return re.sub(pattern, replacement, url)

    return url  # Return original URL if no pattern matches

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Register the custom filters
app.jinja_env.filters['youtube_id'] = youtube_id_filter
app.jinja_env.filters['strftime'] = format_datetime
app.jinja_env.filters['format_datetime'] = format_datetime  # Add an alias for more explicit usage
app.jinja_env.filters['datetimeformat'] = format_datetime  # Add datetimeformat alias for compatibility

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

def generate_otp(length=6):
    """Generate a random numeric OTP of given length"""
    return ''.join(random.choices(string.digits, k=length))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('dashboard.html', username=session.get('username'))
    return redirect(url_for('login'))

# [Previous code remains the same until the quiz-related functions]
# ... (keep all other routes and functions except quiz-related ones)

# Remove or modify the following routes/functions that reference quiz functionality:
# - course_task() - Remove quiz-related code
# - admin_add_task() - Remove quiz-related form handling
# - admin_edit_task() - Remove quiz-related form handling

if __name__ == '__main__':
    app.run(debug=True, port=5000)
