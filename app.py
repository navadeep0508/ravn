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
# from realtime import AuthorizationError, NotConnectedError # This import seems incorrect based on the error

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

def parse_quiz_questions(quiz_text):
    """Parse quiz questions from text format into structured data"""
    if not quiz_text:
        return []

    questions = []
    lines = quiz_text.strip().split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check if this looks like a question (starts with number and dot)
        if re.match(r'^\d+\.', line):
            question_text = line
            options = []
            correct_answer = None

            # Look for options in subsequent lines
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    break

                # Check if this is an option (starts with letter and parenthesis)
                if re.match(r'^[A-Z]\)', next_line):
                    option_text = next_line[3:].strip()  # Remove "A) " prefix
                    options.append(option_text)

                    # Check if this option is marked as correct
                    if 'Correct Answer:' in next_line or '**' in next_line or next_line.endswith('*'):
                        correct_answer = option_text
                elif 'Correct Answer:' in next_line:
                    # Extract correct answer from "Correct Answer: X" format
                    correct_match = re.search(r'Correct Answer:\s*([A-Z])', next_line)
                    if correct_match:
                        correct_letter = correct_match.group(1)
                        if options and len(options) >= ord(correct_letter) - ord('A') + 1:
                            correct_answer = options[ord(correct_letter) - ord('A')]
                    break
                else:
                    break

                j += 1

            # If no correct answer found, try to infer from formatting
            if not correct_answer and options:
                for option in options:
                    if option.endswith('*') or '**' in option:
                        correct_answer = option.replace('*', '').strip()
                        break

            questions.append({
                'question': question_text,
                'options': options,
                'correct_answer': correct_answer or (options[0] if options else '')
            })

            i = j
        else:
            i += 1

    return questions


# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Register the custom filters
app.jinja_env.filters['youtube_id'] = youtube_id_filter
app.jinja_env.filters['parse_quiz_questions'] = parse_quiz_questions

app.jinja_env.filters['strftime'] = format_datetime
app.jinja_env.filters['format_datetime'] = format_datetime  # Add an alias for more explicit usage
app.jinja_env.filters['datetimeformat'] = format_datetime  # Add datetimeformat alias for compatibility

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

# Store OTPs in memory (in production, use Redis or database)
otp_storage = {}
# Store password reset tokens separately
password_reset_storage = {}

def generate_otp(length=6):
    """Generate a random numeric OTP of given length"""
    return ''.join(random.choices(string.digits, k=length))


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Authentication required.'}), 401
            else:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    if 'user_id' in session:
        user_id = session.get('user_id')
        username = session.get('username')

        try:
            # Fetch all courses for recommendations and total count
            courses_result = supabase.table('courses').select('*').eq('status', 'active').execute()
            all_courses = courses_result.data if courses_result.data else []

            # Fetch enrolled courses for the user
            enrolled_courses_result = supabase.table('enrollments').select('course_id, status').eq('student_id', user_id).execute()
            enrolled_course_ids = [e['course_id'] for e in enrolled_courses_result.data] if enrolled_courses_result.data else []

            # Fetch details of enrolled courses
            enrolled_course_details = []
            if enrolled_course_ids:
                enrolled_details_result = supabase.table('courses').select('*').in_('id', enrolled_course_ids).execute()
                enrolled_course_details = enrolled_details_result.data if enrolled_details_result.data else []

            # Calculate progress for each enrolled course
            total_completion_percentage = 0
            completed_courses_count = 0
            for course in enrolled_course_details:
                # This is a simplified progress calculation. A more detailed one would be needed for accuracy.
                progress_result = supabase.table('quiz_attempts').select('score').eq('student_id', user_id).eq('course_id', course['id']).execute()
                scores = [p['score'] for p in progress_result.data] if progress_result.data else []
                course_progress = round(sum(scores) / len(scores)) if scores else 0 # Simplified logic
                course['progress'] = course_progress
                total_completion_percentage += course_progress
                if course_progress >= 100:
                    completed_courses_count += 1

            # Calculate average score from all quiz attempts
            attempts_result = supabase.table('quiz_attempts').select('score').eq('student_id', user_id).execute()
            all_scores = [a['score'] for a in attempts_result.data] if attempts_result.data else []
            average_score = round(sum(all_scores) / len(all_scores)) if all_scores else 0

            # Calculate overall completion rate
            completion_rate = round(total_completion_percentage / len(enrolled_course_details)) if enrolled_course_details else 0

            # Dummy data for other metrics, as logic is not fully implemented
            total_hours = sum([int(c.get('duration', '0').split(' ')[0]) for c in enrolled_course_details if c.get('duration')]) # Simplistic
            leaderboard_rank = 1 # Placeholder
            upcoming_tasks = [] # Placeholder
            recent_activity = [] # Placeholder

            return render_template('dashboard.html',
                                 username=username,
                                 courses=all_courses,
                                 enrolled_courses=len(enrolled_course_ids),
                                 completed_courses=completed_courses_count,
                                 total_hours=total_hours,
                                 enrolled_course_details=enrolled_course_details,
                                 average_score=average_score,
                                 completion_rate=completion_rate,
                                 leaderboard_rank=leaderboard_rank,
                                 upcoming_tasks=upcoming_tasks,
                                 recent_activity=recent_activity)

        except Exception as e:
            import traceback
            print(f"Error loading dashboard: {str(e)}\n{traceback.format_exc()}")
            flash('Could not load dashboard data. Please try again later.', 'error')
            # Render a fallback dashboard with minimal data
            return render_template('dashboard.html', username=username, courses=[], enrolled_courses=0, completed_courses=0, total_hours=0, enrolled_course_details=[], average_score=0, completion_rate=0, leaderboard_rank='N/A', upcoming_tasks=[], recent_activity=[])

    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        otp = request.form.get('otp')
        
        # Initial form validation
        if not all([username, email, password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('signup'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('signup'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('signup'))
        
        # Check if this is OTP verification step
        if 'verifying_otp' in session and session['verifying_otp']:
            stored_otp = otp_storage.get(email, {}).get('otp')
            expiry_time = otp_storage.get(email, {}).get('expiry')
            
            if not stored_otp or datetime.now() > datetime.fromisoformat(expiry_time):
                flash('OTP has expired. Please try again.', 'error')
                session.pop('verifying_otp', None)
                otp_storage.pop(email, None)
                return redirect(url_for('signup'))
            
            if otp != stored_otp:
                flash('Invalid OTP. Please try again.', 'error')
                return render_template('signup.html', 
                                     username=username, 
                                     email=email,
                                     show_otp_field=True)
            
            # OTP verified, proceed with user creation
            try:
                password_hash = generate_password_hash(password)
                # Insert into profiles table
                profile_data = {
                    'name': username,
                    'email': email,
                    'password_hash': password_hash,
                    'role': 'student'
                }
                result = supabase.table('profiles').insert(profile_data).execute()
                
                if result.data and len(result.data) > 0:
                    # Get the new user's ID
                    user_id = result.data[0]['id']
                    
                    # Also add to users table
                    try:
                        user_data = {
                            'id': user_id,
                            'email': email,
                            'full_name': username,
                            'created_at': datetime.utcnow().isoformat(),
                            'updated_at': datetime.utcnow().isoformat()
                        }
                        supabase.table('users').insert(user_data).execute()
                    except Exception as e:
                        print(f"Error adding user to users table: {str(e)}")
                        # Continue with signup even if users table update fails
                
                # Clean up
                session.pop('verifying_otp', None)
                otp_storage.pop(email, None)
                
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('login'))
                
            except Exception as e:
                flash(f'Error creating account: {str(e)}', 'error')
                return redirect(url_for('signup'))
        
        # If we get here, we need to generate and send OTP
        try:
            # Check if email already exists
            existing_user = supabase.table('profiles').select('email').filter('email', 'eq', email).execute()
            if existing_user.data:
                flash('Email already registered.', 'error')
                return redirect(url_for('signup'))
            
            # Generate and store OTP
            otp = generate_otp()
            expiry = (datetime.now() + timedelta(minutes=10)).isoformat()  # OTP valid for 10 minutes
            otp_storage[email] = {
                'otp': otp,
                'expiry': expiry,
                'username': username,
                'password': password
            }
            
            # In production, you would send the OTP via email/SMS here
            print(f"\n{'='*50}")
            print(f"OTP for {email}: {otp}")
            print(f"Expires at: {expiry}")
            print("="*50 + "\n")
            
            # Set session to indicate we're verifying OTP
            session['verifying_otp'] = True
            flash('Verification code sent to your email!', 'info')
            return redirect(url_for('verify_otp', email=email))
            
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('signup'))
    
    # Clear any existing OTP verification state for a fresh start
    session.pop('verifying_otp', None)
    return render_template('signup.html')

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = request.form.get('email')
    if not email:
        flash('Email is required to resend OTP', 'error')
        return redirect(url_for('signup'))
    
    # Generate new OTP
    otp = generate_otp()
    print(otp)
    expiry = (datetime.now() + timedelta(minutes=10)).isoformat()
    
    if email in otp_storage:
        otp_storage[email].update({
            'otp': otp,
            'expiry': expiry
        })
    else:
        otp_storage[email] = {
            'otp': otp,
            'expiry': expiry
        }
    
    # In production, send the OTP via email/SMS
    print(f"\n{'='*50}")
    print(f"NEW OTP for {email}: {otp}")
    print(f"Expires at: {expiry}")
    print("="*50 + "\n")
    
    session['verifying_otp'] = True
    flash('New verification code sent!', 'info')
    return redirect(url_for('verify_otp', email=email))


@app.route('/verify-otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    if request.method == 'POST':
        otp = request.form.get('otp')
        
        if not otp:
            flash('Please enter the verification code.', 'error')
            return redirect(url_for('verify_otp', email=email))
        
        # Verify OTP
        stored_otp = otp_storage.get(email, {}).get('otp')
        expiry_time = otp_storage.get(email, {}).get('expiry')
        
        if not stored_otp or datetime.now() > datetime.fromisoformat(expiry_time):
            flash('OTP has expired. Please request a new one.', 'error')
            otp_storage.pop(email, None)
            return redirect(url_for('signup'))
        
        if otp != stored_otp:
            flash('Invalid verification code. Please try again.', 'error')
            return render_template('verify_otp.html', email=email)
        
        # OTP verified, get user data and create account
        try:
            user_data = otp_storage.get(email, {})
            username = user_data.get('username')
            password = user_data.get('password')
            
            if not username or not password:
                flash('Session expired. Please try signing up again.', 'error')
                return redirect(url_for('signup'))
            
            password_hash = generate_password_hash(password)
            result = supabase.table('profiles').insert({
                'name': username,
                'email': email,
                'password_hash': password_hash,
                'role': 'student'
            }).execute()
            
            # Clean up
            otp_storage.pop(email, None)
            session.pop('verifying_otp', None)
            
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('signup'))
    
    # Check if OTP exists for this email
    if email not in otp_storage:
        flash('Please sign up first to receive a verification code.', 'error')
        return redirect(url_for('signup'))
    
    return render_template('verify_otp.html', email=email)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('login'))
        
        try:
            # Fetch user from Supabase
            result = supabase.table('profiles').select('*').filter('email', 'eq', email).execute()
            
            if result.data and len(result.data) > 0:
                user = result.data[0]
                
                # Verify password
                if check_password_hash(user['password_hash'], password):
                    user_id = str(user['id'])
                    
                    # Check if user exists in users table, if not create
                    try:
                        user_check = supabase.table('users').select('id').eq('id', user_id).execute()
                        if not user_check.data:
                            # Create user in users table
                            user_data = {
                                'id': user_id,
                                'email': user['email'],
                                'full_name': user.get('name', ''),
                                'created_at': datetime.utcnow().isoformat(),
                                'updated_at': datetime.utcnow().isoformat()
                            }
                            supabase.table('users').insert(user_data).execute()
                    except Exception as e:
                        print(f"Error syncing user to users table: {str(e)}")
                        import traceback
                        print(traceback.format_exc())
                    
                    # Set session variables
                    session['user_id'] = user_id
                    session['username'] = user['name']
                    session['user_email'] = user['email']  # Changed from 'email' to 'user_email' to match submit_quiz
                    session['full_name'] = user.get('name', '')
                    session['role'] = user['role']
                    
                    flash(f'Welcome back, {user["name"]}!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid email or password.', 'error')
                    return redirect(url_for('login'))
            else:
                flash('Invalid email or password.', 'error')
                return redirect(url_for('login'))
                
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')


@app.route('/courses')
@login_required
def courses():
    try:
        # Load courses from Supabase
        result = supabase.table('courses').select('*').eq('status', 'active').execute()
        courses = result.data if result.data else []

        # Convert Supabase data format to match template expectations
        formatted_courses = []
        for course in courses:
            formatted_course = {
                'id': course['id'],
                'title': course['title'],
                'description': course['description'],
                'instructor': 'Teacher',  # Will be populated from teacher_uuid later
                'duration': course['duration'],
                'level': course['level'],
                'category': course['category'],
                'price': f"${course['price']}" if course['price'] > 0 else 'Free',
                'students': 0,  # Will be calculated from enrollments
                'rating': '0.0',  # Will be calculated from reviews
                'color': 'blue',  # Default color
                'icon': 'fa-graduation-cap'  # Default icon
            }
            formatted_courses.append(formatted_course)

        # If no courses in database, use sample data for demo
        if not formatted_courses:
            formatted_courses = [
                {
                    'id': 1,
                    'title': 'Mathematics Fundamentals',
                    'description': 'Learn the basics of algebra, geometry, and calculus with hands-on exercises and real-world applications.',
                    'instructor': 'Dr. Sarah Johnson',
                    'duration': '8 weeks',
                    'students': 1247,
                    'rating': '4.8',
                    'level': 'Beginner',
                    'color': 'blue',
                    'icon': 'fa-square-root-alt',
                    'category': 'Mathematics',
                    'price': 'Free',
                    'language': 'English',
                    'skills': ['Algebra', 'Geometry', 'Calculus', 'Problem Solving'],
                    'curriculum': [
                        {'module': 'Week 1-2', 'title': 'Basic Algebra', 'lessons': 5, 'duration': '2 hours'},
                        {'module': 'Week 3-4', 'title': 'Geometry Fundamentals', 'lessons': 6, 'duration': '2.5 hours'},
                        {'module': 'Week 5-6', 'title': 'Introduction to Calculus', 'lessons': 4, 'duration': '3 hours'},
                        {'module': 'Week 7-8', 'title': 'Applications & Review', 'lessons': 3, 'duration': '2 hours'}
                    ],
                    'reviews': [
                        {'name': 'John Doe', 'rating': 5, 'comment': 'Excellent course! Very clear explanations.'},
                        {'name': 'Jane Smith', 'rating': 4, 'comment': 'Good content, but could use more practice problems.'}
                    ]
                },
                {
                    'id': 2,
                    'title': 'Physics for Engineers',
                    'description': 'Comprehensive physics course covering mechanics, thermodynamics, and electromagnetism.',
                    'instructor': 'Prof. Michael Chen',
                    'duration': '12 weeks',
                    'students': 892,
                    'rating': '4.9',
                    'level': 'Intermediate',
                    'color': 'green',
                    'icon': 'fa-atom',
                    'category': 'Physics',
                    'price': '$49',
                    'language': 'English',
                    'skills': ['Mechanics', 'Thermodynamics', 'Electromagnetism', 'Engineering Physics'],
                    'curriculum': [
                        {'module': 'Week 1-3', 'title': 'Classical Mechanics', 'lessons': 8, 'duration': '3 hours'},
                        {'module': 'Week 4-6', 'title': 'Thermodynamics', 'lessons': 6, 'duration': '2.5 hours'},
                        {'module': 'Week 7-9', 'title': 'Electromagnetism', 'lessons': 7, 'duration': '3 hours'},
                        {'module': 'Week 10-12', 'title': 'Applications & Projects', 'lessons': 5, 'duration': '4 hours'}
                    ],
                    'reviews': [
                        {'name': 'Alice Brown', 'rating': 5, 'comment': 'Perfect for engineering students!'},
                        {'name': 'Bob Wilson', 'rating': 5, 'comment': 'Challenging but rewarding course.'}
                    ]
                },
                {
                    'id': 3,
                    'title': 'Computer Science Basics',
                    'description': 'Introduction to programming, data structures, and algorithms for beginners.',
                    'instructor': 'Dr. Emily Rodriguez',
                    'duration': '10 weeks',
                    'students': 2156,
                    'rating': '4.7',
                    'level': 'Beginner',
                    'color': 'purple',
                    'icon': 'fa-code',
                    'category': 'Computer Science',
                    'price': 'Free',
                    'language': 'English',
                    'skills': ['Programming', 'Data Structures', 'Algorithms', 'Problem Solving'],
                    'curriculum': [
                        {'module': 'Week 1-2', 'title': 'Programming Fundamentals', 'lessons': 6, 'duration': '2 hours'},
                        {'module': 'Week 3-5', 'title': 'Data Structures', 'lessons': 8, 'duration': '2.5 hours'},
                        {'module': 'Week 6-8', 'title': 'Algorithms', 'lessons': 7, 'duration': '3 hours'},
                        {'module': 'Week 9-10', 'title': 'Projects & Practice', 'lessons': 4, 'duration': '4 hours'}
                    ],
                    'reviews': [
                        {'name': 'Carol Davis', 'rating': 5, 'comment': 'Great introduction to programming!'},
                        {'name': 'David Lee', 'rating': 4, 'comment': 'Very comprehensive for beginners.'}
                    ]
                }
            ]

        # Get enrolled courses for current user (fetch from database)
        user_id = session.get('user_id')
        if user_id:
            enrolled_result = supabase.table('enrollments').select('course_id').filter('student_id', 'eq', user_id).filter('status', 'eq', 'active').execute()
            enrolled_course_ids = [str(enrollment['course_id']) for enrollment in enrolled_result.data] if enrolled_result.data else []
        else:
            enrolled_course_ids = []

        # Add enrollment status to courses
        for course in formatted_courses:
            # Handle both string and integer IDs
            course_id = course['id']
            if isinstance(course_id, str):
                try:
                    course_id = int(course_id)
                except ValueError:
                    course_id = course['id']

            course['is_enrolled'] = str(course_id) in enrolled_course_ids

        return render_template('courses.html',
                             courses=formatted_courses,
                             enrolled_course_ids=enrolled_course_ids,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/course/<course_id>')
@login_required
def course_detail(course_id):
    # Load courses from Supabase or use sample data
    try:
        result = supabase.table('courses').select('*').execute()
        courses = result.data if result.data else []
    except:
        courses = []

    # If no courses in database, use sample data for demo
    if not courses:
        courses = [
            {
                'id': 'sample1',
                'title': 'Mathematics Fundamentals',
                'description': 'Learn the basics of algebra, geometry, and calculus with hands-on exercises and real-world applications. This comprehensive course covers everything from basic arithmetic to advanced calculus concepts.',
                'instructor': 'Dr. Sarah Johnson',
                'instructor_bio': 'PhD in Mathematics from MIT with 15+ years of teaching experience. Author of "Mathematics Made Simple".',
                'duration': '8 weeks',
                'students': 1247,
                'rating': '4.8',
                'level': 'Beginner',
                'color': 'blue',
                'icon': 'fa-square-root-alt',
                'category': 'Mathematics',
                'price': 'Free',
                'language': 'English',
                'skills': ['Algebra', 'Geometry', 'Calculus', 'Problem Solving'],
                'learning_objectives': [
                    'Master fundamental algebraic concepts and operations',
                    'Understand geometric principles and theorems',
                    'Apply calculus concepts to real-world problems',
                    'Develop critical thinking and problem-solving skills'
                ],
                'prerequisites': ['Basic arithmetic knowledge', 'High school level mathematics'],
                'curriculum': [
                    {
                        'module': 'Week 1-2: Basic Algebra',
                        'title': 'Algebraic Foundations',
                        'lessons': 5,
                        'duration': '2 hours',
                        'topics': ['Variables and expressions', 'Linear equations', 'Quadratic equations', 'Polynomials', 'Factoring']
                    },
                    {
                        'module': 'Week 3-4: Geometry',
                        'title': 'Geometric Principles',
                        'lessons': 6,
                        'duration': '2.5 hours',
                        'topics': ['Points, lines, and planes', 'Angles and triangles', 'Quadrilaterals', 'Circles', '3D geometry']
                    },
                    {
                        'module': 'Week 5-6: Calculus Introduction',
                        'title': 'Limits and Derivatives',
                        'lessons': 4,
                        'duration': '3 hours',
                        'topics': ['Limits and continuity', 'Differentiation rules', 'Applications of derivatives', 'Optimization']
                    },
                    {
                        'module': 'Week 7-8: Applications',
                        'title': 'Real-World Applications',
                        'lessons': 3,
                        'duration': '2 hours',
                        'topics': ['Word problems', 'Data analysis', 'Mathematical modeling', 'Final project']
                    }
                ],
                'reviews': [
                    {'name': 'John Doe', 'rating': 5, 'comment': 'Excellent course! Very clear explanations and practical examples.', 'date': '2 weeks ago'},
                    {'name': 'Jane Smith', 'rating': 4, 'comment': 'Good content, but could use more practice problems.', 'date': '1 month ago'},
                    {'name': 'Mike Johnson', 'rating': 5, 'comment': 'Perfect for refreshing math skills before college.', 'date': '3 weeks ago'}
                ],
                'enrolled_students': 1247,
                'completion_rate': '87%',
                'average_rating': 4.8,
                'last_updated': '2 months ago'
            }
        ]

    # Find course by ID (handle both string and integer IDs)
    course = None
    for c in courses:
        if str(c['id']) == str(course_id):
            course = c
            break

    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('courses'))

    # Check if user is enrolled (check database)
    user_id = session.get('user_id')
    if user_id:
        enrolled_result = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).filter('status', 'eq', 'active').execute()
        is_enrolled = len(enrolled_result.data) > 0 if enrolled_result.data else False
    else:
        is_enrolled = False

    # Calculate progress based on completed tasks
    progress = None
    if is_enrolled and user_id:
        try:
            # Get all modules in the course
            modules_result = supabase.table('modules').select('id').eq('course_id', course_id).execute()
            module_ids = [module['id'] for module in modules_result.data] if modules_result.data else []

            # Get all tasks in these modules
            tasks_result = supabase.table('tasks').select('id').in_('module_id', module_ids).execute()
            total_tasks = len(tasks_result.data) if tasks_result.data else 0

            # Get completed tasks
            if total_tasks > 0:
                task_ids = [task['id'] for task in tasks_result.data]
                completed_tasks_result = supabase.table('progress').select('task_id').eq('student_id', user_id).in_('task_id', task_ids).eq('status', 'completed').execute()
                completed_tasks = len(completed_tasks_result.data) if completed_tasks_result.data else 0

                # Calculate completion percentage
                completion_percentage = round((completed_tasks / total_tasks) * 100, 1)

                # Get last activity
                last_activity_result = supabase.table('progress').select('updated_at').eq('student_id', user_id).in_('task_id', task_ids).order('updated_at', desc=True).limit(1).execute()
                last_activity = last_activity_result.data[0]['updated_at'] if last_activity_result.data else None

                progress = {
                    'completed_lessons': completed_tasks,
                    'total_lessons': total_tasks,
                    'completion_percentage': completion_percentage,
                    'current_module': 'In Progress',  # This can be enhanced to show current module
                    'time_spent': 'Calculating...',  # This would require tracking time spent
                    'last_activity': 'Recently' if last_activity else 'No activity yet'
                }
        except Exception as e:
            print(f"Error calculating progress: {str(e)}")
            progress = {
                'completed_lessons': 0,
                'total_lessons': 0,
                'completion_percentage': 0,
                'current_module': 'Not started',
                'time_spent': '0 hours',
                'last_activity': 'No activity'
            }

    return render_template('course_detail.html',
                         course=course,
                         is_enrolled=is_enrolled,
                         progress=progress,
                         username=session.get('username'))


@app.route('/course/<course_id>/modules')
@login_required
def course_modules(course_id):
    try:
        user_id = session.get('user_id')

        # Check if user is enrolled in this course
        enrolled_result = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).filter('status', 'eq', 'active').execute()
        if not enrolled_result.data:
            flash('You must be enrolled in this course to access its modules.', 'error')
            return redirect(url_for('course_detail', course_id=course_id))

        # Get course details
        course_result = supabase.table('courses').select('*').filter('id', 'eq', course_id).execute()
        if not course_result.data:
            flash('Course not found.', 'error')
            return redirect(url_for('courses'))

        course = course_result.data[0]

        # Get modules for this course
        modules_result = supabase.table('modules').select('*').eq('course_id', course_id).order('order_index').execute()
        modules = modules_result.data if modules_result.data else []

        # Calculate overall progress based on completed tasks
        total_tasks = 0
        completed_tasks = 0

        for module in modules:
            # Get tasks for this module
            module_tasks_result = supabase.table('tasks').select('id').eq('module_id', module['id']).execute()
            module_tasks = module_tasks_result.data if module_tasks_result.data else []
            total_tasks += len(module_tasks)

            # Get completed tasks for this module
            if module_tasks:
                task_ids = [task['id'] for task in module_tasks]
                completed_tasks_result = supabase.table('progress').select('task_id').eq('student_id', user_id).in_('task_id', task_ids).eq('status', 'completed').execute()
                completed_tasks += len(completed_tasks_result.data) if completed_tasks_result.data else 0

        overall_progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Calculate progress for each module based on completed tasks
        user_progress = {}

        for module in modules:
            # Get tasks for this module
            module_tasks_result = supabase.table('tasks').select('id').eq('module_id', module['id']).execute()
            module_tasks = module_tasks_result.data if module_tasks_result.data else []

            if module_tasks:
                task_ids = [task['id'] for task in module_tasks]
                completed_tasks_result = supabase.table('progress').select('task_id').eq('student_id', user_id).in_('task_id', task_ids).eq('status', 'completed').execute()
                completed_tasks = len(completed_tasks_result.data) if completed_tasks_result.data else 0

                # Calculate module progress percentage
                module_progress_percentage = (completed_tasks / len(module_tasks)) * 100

                # Get the most recent progress record for this module
                recent_progress_result = supabase.table('progress').select('*').eq('student_id', user_id).in_('task_id', task_ids).order('updated_at', desc=True).limit(1).execute()

                if recent_progress_result.data:
                    recent_progress = recent_progress_result.data[0]
                    user_progress[str(module['id'])] = {
                        'status': 'completed' if module_progress_percentage >= 100 else 'in_progress',
                        'completion_percentage': round(module_progress_percentage, 1),
                        'updated_at': recent_progress.get('updated_at')
                    }
                else:
                    user_progress[str(module['id'])] = {
                        'status': 'not_started',
                        'completion_percentage': 0
                    }
            else:
                user_progress[str(module['id'])] = {
                    'status': 'not_started',
                    'completion_percentage': 0
                }

        return render_template('course_modules.html',
                             course=course,
                             modules=modules,
                             user_progress=user_progress,
                             overall_progress=round(overall_progress, 1),
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('courses'))

@app.route('/course/<course_id>/module/<module_id>')
@login_required
def course_module_tasks(course_id, module_id):
    try:
        user_id = session.get('user_id')

        # Check if user is enrolled in this course
        enrolled_result = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).filter('status', 'eq', 'active').execute()
        if not enrolled_result.data:
            flash('You must be enrolled in this course to access its modules.', 'error')
            return redirect(url_for('course_detail', course_id=course_id))

        # Get module details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('course_modules', course_id=course_id))

        module = module_result.data[0]

        # Get course details
        course_result = supabase.table('courses').select('*').filter('id', 'eq', course_id).execute()
        course = course_result.data[0] if course_result.data else {}

        # Get tasks for this module
        tasks_result = supabase.table('tasks').select('*').eq('module_id', module_id).order('order_index').execute()
        tasks = tasks_result.data if tasks_result.data else []

        # Get tests for this module
        tests_result = supabase.table('tests').select('*').eq('module_id', module_id).order('order_index').execute()
        tests = tests_result.data if tests_result.data else []

        # Get user progress for tasks in this module
        progress_result = supabase.table('progress').select('*').eq('student_id', user_id).in_('task_id', [str(task['id']) for task in tasks]).execute()
        user_progress = {p['task_id']: p for p in progress_result.data} if progress_result.data else {}

        # Calculate progress for tests (completed attempts)
        test_progress = {}
        for test in tests:
            test_id = test['id']
            # Find quiz tasks associated with this module
            quiz_tasks_result = supabase.table('tasks').select('id').eq('module_id', module_id).eq('type', 'quiz').execute()
            quiz_tasks = quiz_tasks_result.data if quiz_tasks_result.data else []
            
            # Initialize test progress with default values
            test_progress[test_id] = {
                'attempts': 0,
                'best_score': 0,
                'passed': False,
                'completed': False
            }
            
            # Check each quiz task for this module
            for task in quiz_tasks:
                task_id = task['id']
                # Get quiz attempts for this task
                attempts_result = supabase.table('quiz_attempts') \
                    .select('*') \
                    .eq('student_id', user_id) \
                    .eq('task_id', task_id) \
                    .order('created_at', desc=True) \
                    .execute()
                
                attempts = attempts_result.data if attempts_result.data else []
                if attempts:
                    # Update test progress with the best attempt
                    best_attempt = max(attempts, key=lambda x: x.get('score', 0))
                    test_progress[test_id] = {
                        'attempts': len(attempts),
                        'best_score': best_attempt.get('score', 0),
                        'passed': best_attempt.get('passed', False),
                        'completed': best_attempt.get('completed_at') is not None
                    }
                    break  # Use the first quiz task's attempt data

        # Calculate overall module progress
        total_items = len(tasks) + len(tests)
        completed_tasks = sum(1 for p in user_progress.values() if p and p.get('status') == 'completed')
        completed_tests = sum(1 for p in test_progress.values() if p['completed'])
        module_progress = ((completed_tasks + completed_tests) / total_items * 100) if total_items > 0 else 0

        return render_template('course_module_tasks.html',
                             course=course,
                             module=module,
                             tasks=tasks,
                             tests=tests,
                             user_progress=user_progress,
                             test_progress=test_progress,
                             module_progress=round(module_progress, 1),
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('course_modules', course_id=course_id))


@app.route('/course/<course_id>/module/<module_id>/task/<task_id>')
@login_required
def course_task(course_id, module_id, task_id):
    try:
        user_id = session.get('user_id')

        # Check if user is enrolled in this course
        enrolled_result = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).filter('status', 'eq', 'active').execute()
        if not enrolled_result.data:
            flash('You must be enrolled in this course to access its tasks.', 'error')
            return redirect(url_for('course_detail', course_id=course_id))

        # Get task details
        task_result = supabase.table('tasks').select('*').eq('id', task_id).execute()
        if not task_result.data:
            flash('Task not found.', 'error')
            return redirect(url_for('course_module_tasks', course_id=course_id, module_id=module_id))

        task = task_result.data[0]

        # Debug: Print task data to see what's available
        print(f"Task data: {task}")

        # Ensure task has all required fields
        if not hasattr(task, 'get') or 'type' not in task:
            flash('Task data is incomplete.', 'error')
            return redirect(url_for('course_module_tasks', course_id=course_id, module_id=module_id))

        # Verify task belongs to the specified module
        if str(task['module_id']) != str(module_id):
            flash('Task does not belong to this module.', 'error')
            return redirect(url_for('course_module_tasks', course_id=course_id, module_id=module_id))

        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        module = module_result.data[0] if module_result.data else {}

        course_result = supabase.table('courses').select('*').filter('id', 'eq', course_id).execute()
        course = course_result.data[0] if course_result.data else {}

        # Get user progress for this task
        progress_result = supabase.table('progress').select('*').eq('student_id', user_id).eq('task_id', task_id).execute()
        task_progress = progress_result.data[0] if progress_result.data else {}

        # Convert YouTube URL to embed format if it's a video task
        embed_video_url = None
        if task.get('type') == 'video' and task.get('resource_link'):
            embed_video_url = convert_to_youtube_embed(task['resource_link'])

        # Handle quiz data for quiz tasks
        quiz_content = None
        if task.get('type') == 'quiz':
            # Check both 'quiz_data' and 'quiz_content' fields, with fallback to description
            quiz_content = task.get('quiz_data') or task.get('quiz_content') or task.get('description', '')
            
            # Debug output
            print(f"Quiz content from DB: {quiz_content}")
            
            # If we have quiz content, try to parse it to ensure it's valid
            if quiz_content:
                try:
                    questions = parse_quiz_questions(quiz_content)
                    print(f"Successfully parsed {len(questions)} questions from quiz data")
                except Exception as e:
                    print(f"Error parsing quiz data: {str(e)}")
                    quiz_content = None

        # Initialize or update task progress when starting
        if not task_progress:
            # Create initial progress record
            try:
                supabase.table('progress').insert({
                    'student_id': user_id,
                    'course_id': course_id,
                    'module_id': module_id,
                    'task_id': task_id,
                    'status': 'in_progress'
                }).execute()
            except Exception as e:
                # If RLS policy fails, try with admin bypass
                try:
                    supabase.rpc('disable_rls_for_admin', params={}).execute()
                    supabase.table('progress').insert({
                        'student_id': user_id,
                        'course_id': course_id,
                        'module_id': module_id,
                        'task_id': task_id,
                        'status': 'in_progress'
                    }).execute()
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                    raise e
            task_progress = {'status': 'in_progress', 'completion_percentage': 0}

        return render_template('course_task.html',
                             course=course,
                             module=module,
                             task=task,
                             task_progress=task_progress,
                             embed_video_url=embed_video_url,
                             quiz_content=quiz_content,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('course_module_tasks', course_id=course_id, module_id=module_id))



@app.route('/course/<course_id>/module/<module_id>/task/<task_id>/complete', methods=['POST'])
@login_required
def complete_task(course_id, module_id, task_id):
    try:
        user_id = session.get('user_id')

        # Verify user is enrolled
        enrolled_result = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).filter('status', 'eq', 'active').execute()
        if not enrolled_result.data:
            flash('You must be enrolled in this course.', 'error')
            return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))

        # Update task progress to completed
        from datetime import datetime
        supabase.table('progress').update({
            'status': 'completed',
            'completion_percentage': 100,
            'completed_at': datetime.utcnow().isoformat(),  # type: ignore
        }).filter('student_id', 'eq', user_id).filter('task_id', 'eq', task_id).execute()

        flash('Task completed successfully!', 'success')
        return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))

    except Exception as e:
        flash(f'Error completing task: {str(e)}', 'error')
        return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))


@app.route('/course/<course_id>/enroll', methods=['POST'])
@login_required
def enroll_course(course_id):
    try:
        user_id = session.get('user_id')

        # Check if already enrolled
        existing_enrollment = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).execute()
        if existing_enrollment.data:
            flash('You are already enrolled in this course.', 'info')
            return redirect(url_for('course_detail', course_id=course_id))

        # Find course title by ID
        course_title = "Course"
        try:
            result = supabase.table('courses').select('title').filter('id', 'eq', course_id).execute()
            if result.data and len(result.data) > 0:
                course_title = result.data[0]['title']
        except:
            course_title = "Course"

        # Insert enrollment record
        try:
            supabase.table('enrollments').insert({
                'student_id': user_id,
                'course_id': course_id,
                'status': 'active'
            }).execute()
        except Exception as e:
            # If RLS policy fails, try with admin bypass
            try:
                supabase.rpc('disable_rls_for_admin', params={}).execute()
                supabase.table('enrollments').insert({
                    'student_id': user_id,
                    'course_id': course_id,
                    'status': 'active'
                }).execute()
                supabase.rpc('enable_rls_for_admin', params={}).execute()
            except:
                supabase.rpc('enable_rls_for_admin', params={}).execute()
                raise e

        flash(f'Successfully enrolled in {course_title}!', 'success')
        return redirect(url_for('course_detail', course_id=course_id))
    except Exception as e:
        flash(f'Error enrolling in course: {str(e)}', 'error')
        return redirect(url_for('course_detail', course_id=course_id))


@app.route('/course/<course_id>/unenroll', methods=['POST'])
@login_required
def unenroll_course(course_id):
    try:
        user_id = session.get('user_id')

        # Find course title by ID
        course_title = "Course"
        try:
            result = supabase.table('courses').select('title').filter('id', 'eq', course_id).execute()
            if result.data and len(result.data) > 0:
                course_title = result.data[0]['title']
        except:
            course_title = "Course"

        # Remove enrollment record
        try:
            supabase.table('enrollments').delete().filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).execute()
        except Exception as e:
            # If RLS policy fails, try with admin bypass
            try:
                supabase.rpc('disable_rls_for_admin', params={}).execute()
                supabase.table('enrollments').delete().filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).execute()
                supabase.rpc('enable_rls_for_admin', params={}).execute()
            except:
                supabase.rpc('enable_rls_for_admin', params={}).execute()
                raise e

        flash(f'Successfully unenrolled from {course_title}.', 'success')
        return redirect(url_for('course_detail', course_id=course_id))
    except Exception as e:
        flash(f'Error unenrolling from course: {str(e)}', 'error')
        return redirect(url_for('course_detail', course_id=course_id))


@app.route('/profile')
@login_required
def profile():
    try:
        # Fetch user data from Supabase
        user_id = session.get('user_id')
        result = supabase.table('profiles').select('*').eq('id', user_id).execute()

        if result.data and len(result.data) > 0:
            user_data = result.data[0]
            return render_template('profile.html',
                                 user=user_data,
                                 username=session.get('username'))
        else:
            flash('User profile not found.', 'error')
            return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error fetching profile: {str(e)}', 'error')
        import traceback
        print(traceback.format_exc())
        return redirect(url_for('dashboard'))


@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    try:
        # Fetch current user data
        user_id = session.get('user_id')
        result = supabase.table('profiles').select('*').eq('id', user_id).execute()

        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            # Verify current password if changing password
            if current_password or new_password or confirm_password:
                if not all([current_password, new_password, confirm_password]):
                    flash('All password fields are required for password change.', 'error')
                    return redirect(url_for('edit_profile'))
                
                if new_password != confirm_password:
                    flash('New passwords do not match.', 'error')
                    return redirect(url_for('edit_profile'))
                
                if not check_password_hash(result.data[0]['password_hash'], current_password):
                    flash('Current password is incorrect.', 'error')
                    return redirect(url_for('edit_profile'))
                
                # Update password
                password_hash = generate_password_hash(new_password)
                supabase.table('profiles').update({'password_hash': password_hash}).eq('id', user_id).execute()
                flash('Password updated successfully!', 'success')

            # Update profile
            supabase.table('profiles').update({
                'name': name,
                'email': email
            }).eq('id', user_id).execute()

            # Update session
            session['username'] = name
            session['user_email'] = email
            
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))

        # For GET request, show the form with current data
        if result.data and len(result.data) > 0:
            user_data = result.data[0]
            return render_template('edit_profile.html',
                                 user=user_data,
                                 username=session.get('username'))
        else:
            flash('User profile not found.', 'error')
            return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f'Error updating profile: {str(e)}', 'error')
        import traceback
        print(traceback.format_exc())
        return redirect(url_for('profile'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('forgot_password'))

        try:
            # Check if email exists in database
            existing_user = supabase.table('profiles').select('email').filter('email', 'eq', email).execute()
            if not existing_user.data:
                flash('No account found with this email address.', 'error')
                return redirect(url_for('forgot_password'))

            # Generate and store password reset OTP
            reset_otp = generate_otp()
            expiry = (datetime.now() + timedelta(minutes=10)).isoformat()
            password_reset_storage[email] = {
                'otp': reset_otp,
                'expiry': expiry
            }

            # In production, you would send the OTP via email/SMS here
            print(f"\n{'='*50}")
            print(f"PASSWORD RESET OTP for {email}: {reset_otp}")
            print(f"Expires at: {expiry}")
            print("="*50 + "\n")

            flash('Password reset code sent to your email!', 'info')
            return redirect(url_for('verify_reset_otp', email=email))

        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')


@app.route('/verify-reset-otp/<email>', methods=['GET', 'POST'])
def verify_reset_otp(email):
    if request.method == 'POST':
        otp = request.form.get('otp')

        if not otp:
            flash('Please enter the reset code.', 'error')
            return redirect(url_for('verify_reset_otp', email=email))

        # Verify password reset OTP
        stored_otp = password_reset_storage.get(email, {}).get('otp')
        expiry_time = password_reset_storage.get(email, {}).get('expiry')

        if not stored_otp or datetime.now() > datetime.fromisoformat(expiry_time):
            flash('Reset code has expired. Please request a new one.', 'error')
            password_reset_storage.pop(email, None)
            return redirect(url_for('forgot_password'))

        if otp != stored_otp:
            flash('Invalid reset code. Please try again.', 'error')
            return render_template('verify_reset_otp.html', email=email)

        # Reset OTP verified, redirect to new password page
        flash('Reset code verified! Please set your new password.', 'success')
        return redirect(url_for('set_new_password', email=email))

    # Check if reset OTP exists for this email
    if email not in password_reset_storage:
        flash('Please request a password reset first.', 'error')
        return redirect(url_for('forgot_password'))

    return render_template('verify_reset_otp.html', email=email)


@app.route('/resend-reset-otp', methods=['POST'])
def resend_reset_otp():
    email = request.form.get('email')
    if not email:
        flash('Email is required to resend reset code', 'error')
        return redirect(url_for('forgot_password'))

    # Generate new password reset OTP
    reset_otp = generate_otp()
    expiry = (datetime.now() + timedelta(minutes=10)).isoformat()

    if email in password_reset_storage:
        password_reset_storage[email].update({
            'otp': reset_otp,
            'expiry': expiry
        })
    else:
        password_reset_storage[email] = {
            'otp': reset_otp,
            'expiry': expiry
        }

    # In production, send the OTP via email/SMS
    print(f"\n{'='*50}")
    print(f"NEW PASSWORD RESET OTP for {email}: {reset_otp}")
    print(f"Expires at: {expiry}")
    print("="*50 + "\n")

    flash('New reset code sent!', 'info')
    return redirect(url_for('verify_reset_otp', email=email))


@app.route('/set-new-password/<email>', methods=['GET', 'POST'])
def set_new_password(email):
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validation
        if not new_password or not confirm_password:
            flash('Both password fields are required.', 'error')
            return redirect(url_for('set_new_password', email=email))

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('set_new_password', email=email))

        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('set_new_password', email=email))

        try:
            # Verify user exists
            existing_user = supabase.table('profiles').select('email').filter('email', 'eq', email).execute()
            if not existing_user.data:
                flash('Invalid request. Please try again.', 'error')
                return redirect(url_for('forgot_password'))

            # Hash new password and update
            new_password_hash = generate_password_hash(new_password)
            supabase.table('profiles').update({
                'password_hash': new_password_hash
            }).filter('email', 'eq', email).execute()

            # Clean up
            password_reset_storage.pop(email, None)

            flash('Password updated successfully! Please log in with your new password.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('set_new_password', email=email))

    # Check if user has permission to reset password (has valid reset token)
    if email not in password_reset_storage:
        flash('Please request a password reset first.', 'error')
        return redirect(url_for('forgot_password'))

    return render_template('set_new_password.html', email=email)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Authentication required.'}), 401
            else:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))

        # Check if user is admin
        user_id = session.get('user_id')
        result = supabase.table('profiles').select('role').filter('id', 'eq', user_id).execute()
        if result.data and result.data[0]['role'] == 'admin':
            return f(*args, **kwargs)
        else:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('dashboard'))
    return decorated_function


@app.route('/dashboard')
@login_required
def dashboard():
    try:
        user_id = session.get('user_id')

        # Calculate statistics dynamically from database
        # Total courses available
        courses_result = supabase.table('courses').select('*').eq('status', 'active').execute()
        total_courses = len(courses_result.data) if courses_result.data else 0

        # User's enrolled courses
        enrolled_result = supabase.table('enrollments').select('*').eq('student_id', user_id).eq('status', 'active').execute()
        enrolled_courses = len(enrolled_result.data) if enrolled_result.data else 0

        # User's completed courses (where progress >= 100%)
        completed_result = supabase.table('enrollments').select('*').eq('student_id', user_id).eq('status', 'completed').execute()
        completed_courses = len(completed_result.data) if completed_result.data else 0

        # Calculate total hours (sum of course durations for enrolled courses)
        total_hours = 0
        if enrolled_result.data:
            for enrollment in enrolled_result.data:
                course_result = supabase.table('courses').select('duration').eq('id', enrollment['course_id']).execute()
                if course_result.data:
                    # Try to extract numeric hours from duration string
                    duration = course_result.data[0]['duration']
                    # Simple extraction - you might want to improve this parsing
                    import re
                    hours_match = re.search(r'(\d+)', str(duration))
                    if hours_match:
                        total_hours += int(hours_match.group(1))

        # Calculate real performance metrics
        # Average Score from quiz attempts
        quiz_attempts_result = supabase.table('quiz_attempts').select('*').eq('student_id', user_id).execute()
        average_score = 0
        if quiz_attempts_result.data:
            scores = [attempt['score'] for attempt in quiz_attempts_result.data if attempt['score'] is not None]
            if scores:
                average_score = round(sum(scores) / len(scores), 1)

        # Completion Rate (percentage of completed tasks vs total enrolled tasks)
        completion_rate = 0
        if enrolled_result.data:
            total_tasks = 0
            completed_tasks = 0

            for enrollment in enrolled_result.data:
                course_id = enrollment['course_id']

                # Get modules for this course
                modules_result = supabase.table('modules').select('id').eq('course_id', course_id).execute()
                if modules_result.data:
                    module_ids = [module['id'] for module in modules_result.data]

                    # Get tasks for these modules
                    if module_ids:
                        tasks_result = supabase.table('tasks').select('id').in_('module_id', module_ids).execute()
                        if tasks_result.data:
                            task_ids = [task['id'] for task in tasks_result.data]
                            total_tasks += len(task_ids)

                            # Count completed tasks
                            if task_ids:
                                completed_tasks_result = supabase.table('progress').select('id').eq('student_id', user_id).in_('task_id', task_ids).eq('status', 'completed').execute()
                                completed_tasks += len(completed_tasks_result.data) if completed_tasks_result.data else 0

            if total_tasks > 0:
                completion_rate = round((completed_tasks / total_tasks) * 100, 1)

        # Leaderboard Rank (based on completion rate and total hours)
        # This is a simplified ranking - you might want to implement a more sophisticated algorithm
        all_students_result = supabase.table('profiles').select('id').eq('role', 'student').execute()
        leaderboard_rank = 1  # Default rank

        if all_students_result.data and len(all_students_result.data) > 1:
            # Calculate a score based on completion rate and hours
            user_score = completion_rate * 0.7 + (total_hours / 100) * 0.3  # Weighted score

            for student in all_students_result.data:
                if student['id'] == user_id:
                    continue

                student_completion = 0
                student_hours = 0

                # Get student's completion rate and hours (simplified calculation)
                student_enrollments = supabase.table('enrollments').select('*').eq('student_id', student['id']).eq('status', 'active').execute()
                if student_enrollments.data:
                    # Simplified calculation for demo - you might want to implement proper calculation
                    student_score = 50  # Placeholder

                    if student_score > user_score:
                        leaderboard_rank += 1

        # Fetch enrolled course details for display
        enrolled_course_details = []
        if enrolled_result.data:
            for enrollment in enrolled_result.data:
                course_result = supabase.table('courses').select('*').eq('id', enrollment['course_id']).execute()
                if course_result.data:
                    course = course_result.data[0]
                    enrolled_course_details.append({
                        'id': course['id'],
                        'title': course['title'],
                        'description': course['description'][:100] + '...' if len(course['description']) > 100 else course['description'],
                        'duration': course['duration'],
                        'level': course['level'],
                        'category': course['category'],
                        'progress': calculate_course_progress(user_id, course['id']) if 'calculate_course_progress' in globals() else 0,
                        'enrolled_at': enrollment['enrolled_at']
                    })

        # Fetch upcoming deadlines (assignments with due dates)
        upcoming_tasks = []
        if enrolled_result.data:
            for enrollment in enrolled_result.data:
                course_id = enrollment['course_id']

                # Get modules for this course
                modules_result = supabase.table('modules').select('id').eq('course_id', course_id).execute()
                if modules_result.data:
                    module_ids = [module['id'] for module in modules_result.data]

                    # Get tasks for these modules that have due dates
                    if module_ids:
                        tasks_result = supabase.table('tasks').select('*').in_('module_id', module_ids).not_.is_('due_date', None).execute()
                        if tasks_result.data:
                            for task in tasks_result.data:
                                # Check if task is not completed by this user
                                progress_result = supabase.table('progress').select('status').eq('student_id', user_id).eq('task_id', task['id']).execute()
                                if not progress_result.data or progress_result.data[0]['status'] != 'completed':
                                    upcoming_tasks.append({
                                        'id': task['id'],
                                        'title': task['title'],
                                        'type': task['type'],
                                        'due_date': task['due_date'],
                                        'course_id': course_id,
                                        'module_id': task['module_id']
                                    })

        # Sort by due date and take next 5
        upcoming_tasks.sort(key=lambda x: x['due_date'] if x['due_date'] else '9999-12-31')
        upcoming_tasks = upcoming_tasks[:5]

        # Fetch recent notifications/activity
        recent_activity = []

        # Recent completed tasks (last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        completed_recently = supabase.table('progress').select('*, tasks(title), courses(title)').eq('student_id', user_id).eq('status', 'completed').gte('completed_at', week_ago).execute()

        if completed_recently.data:
            for activity in completed_recently.data[:3]:  # Take 3 most recent
                task_title = activity.get('tasks', {}).get('title', 'Task') if activity.get('tasks') else 'Task'
                course_title = activity.get('courses', {}).get('title', 'Course') if activity.get('courses') else 'Course'

                recent_activity.append({
                    'type': 'completion',
                    'message': f"Completed '{task_title}' in '{course_title}'",
                    'time_ago': 'Recently',
                    'icon': 'check',
                    'color': 'green'
                })

        # Recent enrollments (last 7 days)
        recent_enrollments = supabase.table('enrollments').select('*, courses(title)').eq('student_id', user_id).gte('enrolled_at', week_ago).execute()
        if recent_enrollments.data:
            for enrollment in recent_enrollments.data[:2]:  # Take 2 most recent
                course_title = enrollment.get('courses', {}).get('title', 'Course') if enrollment.get('courses') else 'Course'

                recent_activity.append({
                    'type': 'enrollment',
                    'message': f"Enrolled in '{course_title}'",
                    'time_ago': 'Recently',
                    'icon': 'graduation-cap',
                    'color': 'blue'
                })

        # If no recent activity, add a welcome message
        if not recent_activity:
            recent_activity.append({
                'type': 'welcome',
                'message': "Welcome to your learning dashboard!",
                'time_ago': 'Today',
                'icon': 'info-circle',
                'color': 'indigo'
            })

        return render_template('dashboard.html',
                             username=session.get('username'),
                             courses=courses_result.data if courses_result.data else [],
                             enrolled_courses=enrolled_courses,
                             completed_courses=completed_courses,
                             total_hours=total_hours,
                             enrolled_course_details=enrolled_course_details,
                             average_score=average_score,
                             completion_rate=completion_rate,
                             leaderboard_rank=leaderboard_rank,
                             upcoming_tasks=upcoming_tasks,
                             recent_activity=recent_activity)

    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        # Fallback to sample data
        enrolled_courses = 2
        completed_courses = 1
        total_hours = 48

        return render_template('dashboard.html',
                             username=session.get('username'),
                             enrolled_courses=enrolled_courses,
                             completed_courses=completed_courses,
                             total_hours=total_hours)


@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        # Get system statistics
        users_result = supabase.table('profiles').select('*').execute()
        users_data = users_result.data if users_result.data else []

        total_users = len(users_data)

        # Count users by role safely
        students = len([user for user in users_data if user.get('role') == 'student'])
        teachers = len([user for user in users_data if user.get('role') == 'teacher'])
        admins = len([user for user in users_data if user.get('role') == 'admin'])

        # Recent users (last 5)
        recent_users = users_data[-5:] if users_data else []

        return render_template('admin_dashboard.html',
                             total_users=total_users,
                             students=students,
                             teachers=teachers,
                             admins=admins,
                             recent_users=recent_users,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        # Get all users
        result = supabase.table('profiles').select('*').order('created_at', desc=True).execute()
        users = result.data if result.data else []

        return render_template('admin_users.html',
                             users=users,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/users/edit/<user_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(user_id):
    try:
        # Get user data
        result = supabase.table('profiles').select('*').filter('id', user_id).execute()
        if not result.data:
            flash('User not found.', 'error')
            return redirect(url_for('admin_users'))

        user_data = result.data[0]

        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            role = request.form.get('role')

            # Validate required fields
            if not all([name, email, role]):
                flash('All fields are required.', 'error')
                return render_template('admin_edit_user.html',
                                     user=user_data,
                                     username=session.get('username'))

            # Check if email is already taken by another user
            existing_user = supabase.table('profiles').select('id').filter('email', 'eq', email).neq('id', user_id).execute()
            if existing_user.data:
                flash('Email is already registered to another account.', 'error')
                return render_template('admin_edit_user.html',
                                     user=user_data,
                                     username=session.get('username'))

            # Update user data
            supabase.table('profiles').update({
                'name': name,
                'email': email,
                'role': role
            }).filter('id', user_id).execute()

            flash('User updated successfully!', 'success')
            return redirect(url_for('admin_users'))

        return render_template('admin_edit_user.html',
                             user=user_data,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_users'))


@app.route('/admin/users/delete/<user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    try:
        # Prevent admin from deleting themselves
        if user_id == session.get('user_id'):
            flash('You cannot delete your own account.', 'error')
            return redirect(url_for('admin_users'))

        # Delete user
        supabase.table('profiles').delete().filter('id', 'eq', user_id).execute()

        flash('User deleted successfully!', 'success')
        return redirect(url_for('admin_users'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_users'))


@app.route('/admin/courses')
@admin_required
def admin_courses():
    try:
        # Load courses from Supabase
        result = supabase.table('courses').select('*').order('created_at', desc=True).execute()
        courses = result.data if result.data else []

        # Convert Supabase data format to match template expectations
        formatted_courses = []
        for course in courses:
            formatted_course = {
                'id': course['id'],
                'title': course['title'],
                'description': course['description'],
                'instructor': 'Teacher',  # Will be populated from teacher_uuid later
                'duration': course['duration'],
                'level': course['level'],
                'category': course['category'],
                'price': f"${course['price']}" if course['price'] > 0 else 'Free',
                'status': course['status'],
                'students': 0,  # Will be calculated from enrollments
                'rating': '0.0',  # Will be calculated from reviews
                'color': 'blue',  # Default color
                'icon': 'fa-graduation-cap'  # Default icon
            }
            formatted_courses.append(formatted_course)

        # If no courses in database, use sample data for demo
        if not formatted_courses:
            formatted_courses = [
                {
                    'id': 'sample1',
                    'title': 'Mathematics Fundamentals',
                    'description': 'Learn the basics of algebra, geometry, and calculus.',
                    'instructor': 'Dr. Sarah Johnson',
                    'duration': '8 weeks',
                    'students': 1247,
                    'rating': '4.8',
                    'level': 'Beginner',
                    'status': 'active',
                    'category': 'Mathematics',
                    'color': 'blue',
                    'icon': 'fa-square-root-alt'
                },
                {
                    'id': 'sample2',
                    'title': 'Physics for Engineers',
                    'description': 'Comprehensive physics course covering mechanics and thermodynamics.',
                    'instructor': 'Prof. Michael Chen',
                    'duration': '12 weeks',
                    'students': 892,
                    'rating': '4.9',
                    'level': 'Intermediate',
                    'status': 'active',
                    'category': 'Physics',
                    'color': 'green',
                    'icon': 'fa-atom'
                },
                {
                    'id': 'sample3',
                    'title': 'Computer Science Basics',
                    'description': 'Introduction to programming and algorithms.',
                    'instructor': 'Dr. Emily Rodriguez',
                    'duration': '10 weeks',
                    'students': 2156,
                    'rating': '4.7',
                    'level': 'Beginner',
                    'status': 'active',
                    'category': 'Computer Science',
                    'color': 'purple',
                    'icon': 'fa-code'
                }
            ]

        # Calculate statistics
        total_courses = len(formatted_courses)
        total_students = sum(course.get('students', 0) for course in formatted_courses)
        average_rating = 0.0
        if formatted_courses:
            ratings = [float(course.get('rating', '0')) for course in formatted_courses if course.get('rating')]
            if ratings:
                average_rating = sum(ratings) / len(ratings)

        # Calculate additional stats
        active_courses = len([c for c in formatted_courses if c.get('status') == 'active'])
        inactive_courses = len([c for c in formatted_courses if c.get('status') == 'inactive'])
        draft_courses = len([c for c in formatted_courses if c.get('status') == 'draft'])

        return render_template('admin_courses.html',
                             courses=formatted_courses,
                             total_courses=total_courses,
                             total_students=total_students,
                             average_rating=round(average_rating, 1),
                             active_courses=active_courses,
                             inactive_courses=inactive_courses,
                             draft_courses=draft_courses,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/courses/add', methods=['GET', 'POST'])
@admin_required
def admin_add_course():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        instructor = request.form.get('instructor')
        duration = request.form.get('duration')
        level = request.form.get('level')
        category = request.form.get('category', 'General')
        price = request.form.get('price', 'Free')
        status = request.form.get('status', 'active')

        # Validate required fields
        if not all([title, description, instructor, duration, level]):
            flash('All fields are required.', 'error')
            return render_template('admin_add_course.html',
                                 username=session.get('username'))

        try:
            # Generate course UUID
            import uuid
            course_uuid = str(uuid.uuid4())

            # Get current user ID for teacher_uuid
            user_id = session.get('user_id')

            # Insert course into Supabase
            result = supabase.table('courses').insert({
                'id': course_uuid,
                'title': title,
                'description': description,
                'category': category,
                'level': level,
                'duration': duration,
                'language': 'English',
                'teacher_uuid': user_id,
                'price': 0 if price == 'Free' else float(price.replace('$', '')),
                'status': status
            }).execute()

            flash(f'Course "{title}" added successfully!', 'success')
            return redirect(url_for('admin_courses'))

        except Exception as e:
            flash(f'Error creating course: {str(e)}', 'error')
            return render_template('admin_add_course.html',
                                 username=session.get('username'))

    return render_template('admin_add_course.html',
                         username=session.get('username'))


@app.route('/admin/courses/edit/<course_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_course(course_id):
    try:
        # Get course details
        course_result = supabase.table('courses').select('*').filter('id', 'eq', course_id).execute()
        if not course_result.data:
            flash('Course not found.', 'error')
            return redirect(url_for('admin_courses'))

        course = course_result.data[0]

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            level = request.form.get('level')
            category = request.form.get('category', 'General')
            duration = request.form.get('duration')
            price = request.form.get('price', 'Free')
            status = request.form.get('status', 'active')

            # Validate required fields
            if not all([title, description, level, duration]):
                flash('All fields are required.', 'error')
                return render_template('admin_edit_course.html',
                                     course=course,
                                     username=session.get('username'))

            try:
                # Update course in Supabase
                supabase.table('courses').update({
                    'title': title,
                    'description': description,
                    'level': level,
                    'category': category,
                    'duration': duration,
                    'price': 0 if price == 'Free' else float(price.replace('$', '')),
                    'status': status
                }).filter('id', 'eq', course_id).execute()

                flash(f'Course "{title}" updated successfully!', 'success')
                return redirect(url_for('admin_courses'))

            except Exception as e:
                flash(f'Error updating course: {str(e)}', 'error')
                return render_template('admin_edit_course.html',
                                     course=course,
                                     username=session.get('username'))

        return render_template('admin_edit_course.html',
                             course=course,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/courses/<course_id>/modules')
@admin_required
def admin_course_modules(course_id):
    try:
        # Get course details
        course_result = supabase.table('courses').select('*').filter('id', 'eq', course_id).execute()
        if not course_result.data:
            flash('Course not found.', 'error')
            return redirect(url_for('admin_courses'))

        course = course_result.data[0]

        # Get modules for this course
        modules_result = supabase.table('modules').select('*').eq('course_id', course_id).order('order_index').execute()
        modules = modules_result.data if modules_result.data else []

        return render_template('admin_course_modules.html',
                             course=course,
                             modules=modules,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/courses/<course_id>/modules/add', methods=['GET', 'POST'])
@admin_required
def admin_add_module(course_id):
    try:
        # Verify course exists and user has permission
        course_result = supabase.table('courses').select('*').filter('id', 'eq', course_id).execute()
        if not course_result.data:
            flash('Course not found.', 'error')
            return redirect(url_for('admin_courses'))

        course = course_result.data[0]

        # Check if user is the teacher or admin
        user_id = session.get('user_id')
        if course['teacher_uuid'] != user_id and not (supabase.table('profiles').select('role').filter('id', user_id).execute().data[0]['role'] == 'admin'):
            flash('Access denied.', 'error')
            return redirect(url_for('admin_courses'))

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            order_index = request.form.get('order_index', 1)
            estimated_time = request.form.get('estimated_time', '1 hour')

            # Validate required fields
            if not all([title, description]):
                flash('Title and description are required.', 'error')
                return render_template('admin_add_module.html',
                                     course=course,
                                     username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Insert new module
                result = supabase.table('modules').insert({
                    'course_id': course_id,
                    'title': title,
                    'description': description,
                    'order_index': int(order_index),
                    'estimated_time': estimated_time
                }).execute()

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Module "{title}" added successfully!', 'success')
                return redirect(url_for('admin_course_modules', course_id=course_id))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    pass
                flash(f'Error creating module: {str(e)}', 'error')
                return render_template('admin_add_module.html',
                                     course=course,
                                     username=session.get('username'))

        return render_template('admin_add_module.html',
                             course=course,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/modules/edit/<module_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_module(module_id):
    try:
        # Get module details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]

        # Get course details
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            order_index = request.form.get('order_index', 1)
            estimated_time = request.form.get('estimated_time', '1 hour')

            # Validate required fields
            if not all([title, description]):
                flash('Title and description are required.', 'error')
                return render_template('admin_edit_module.html',
                                     module=module,
                                     course=course,
                                     username=session.get('username'))

            try:
                # Update module in Supabase
                supabase.table('modules').update({
                    'title': title,
                    'description': description,
                    'order_index': int(order_index),
                    'estimated_time': estimated_time
                }).eq('id', module_id).execute()

                flash(f'Module "{title}" updated successfully!', 'success')
                return redirect(url_for('admin_course_modules', course_id=course['id']))

            except Exception as e:
                flash(f'Error updating module: {str(e)}', 'error')
                return render_template('admin_edit_module.html',
                                     module=module,
                                     course=course,
                                     username=session.get('username'))

        return render_template('admin_edit_module.html',
                             module=module,
                             course=course,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/modules/<module_id>/tasks')
@admin_required
def admin_module_tasks(module_id):
    try:
        # Get module details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]

        # Get course details
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        # Get tasks for this module
        tasks_result = supabase.table('tasks').select('*').eq('module_id', module_id).order('order_index').execute()
        tasks = tasks_result.data if tasks_result.data else []

        return render_template('admin_module_tasks.html',
                             module=module,
                             course=course,
                             tasks=tasks,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/tasks/edit/<task_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_task(task_id):
    try:
        # Get task details
        task_result = supabase.table('tasks').select('*').filter('id', 'eq', task_id).execute()
        if not task_result.data:
            flash('Task not found.', 'error')
            return redirect(url_for('admin_courses'))

        task = task_result.data[0]

        # Parse existing quiz questions if this is a quiz task
        existing_questions = []
        if task.get('type') == 'quiz' and task.get('quiz_data'):
            try:
                # Try to parse as new JSON format first
                quiz_data = json.loads(task['quiz_data'])
                if isinstance(quiz_data, dict) and 'version' in quiz_data:
                    # New format
                    existing_questions = quiz_data.get('questions', [])
                else:
                    # Fall back to old format
                    existing_questions = parse_quiz_questions(task['quiz_data'])
            except (json.JSONDecodeError, TypeError):
                # Handle case where quiz_data is not valid JSON
                existing_questions = parse_quiz_questions(task['quiz_data'])

        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', task['module_id']).execute()
        module = module_result.data[0] if module_result.data else {}

        course_result = supabase.table('courses').select('*').eq('id', module.get('course_id')).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            task_type = request.form.get('type')
            order_index = request.form.get('order_index', 1)
            estimated_time = request.form.get('estimated_time', '30 minutes')
            # Handle resource_link based on task type
            form_resource_link = request.form.get('resource_link', '').strip()
            current_resource_link = task.get('resource_link', '')

            # If form has a resource_link value, use it; otherwise keep current value
            if form_resource_link:
                resource_link = form_resource_link
            else:
                resource_link = current_resource_link

            print(f"DEBUG: Edit task - form_resource_link='{form_resource_link}', current_resource_link='{current_resource_link}', final_resource_link='{resource_link}'")
            is_mandatory = request.form.get('is_mandatory') == 'on'

            # Handle quiz-specific settings

            if task_type == 'assignment':
                assignment_instructions = request.form.get('assignment_instructions', '')
                due_date = request.form.get('due_date')
                max_file_size = int(request.form.get('max_file_size', 10))
                allow_late_submissions = request.form.get('allow_late_submissions') == 'on'

                # Use assignment_instructions for task description
                description = f'Assignment: {assignment_instructions[:100]}...' if assignment_instructions else 'Assignment submission required'

            # Handle reading-specific settings
            elif task_type == 'reading':
                reading_instructions = request.form.get('reading_instructions', '')

            # Handle discussion-specific settings
            elif task_type == 'discussion':
                discussion_prompt = request.form.get('discussion_prompt', '')
                min_posts_required = int(request.form.get('min_posts_required', 1))
                discussion_duration_days = request.form.get('discussion_duration_days', '7')
                require_replies = request.form.get('require_replies') == 'on'

            # Validate required fields
            if not all([title, description, task_type]):
                flash('Title, description, and type are required.', 'error')
                return render_template('admin_edit_task.html',
                                     task=task,
                                     module=module,
                                     course=course,
                                     username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Prepare task data
                update_data = {
                    'title': title,
                    'description': description,
                    'type': task_type,
                    'order_index': int(order_index),
                    'estimated_time': estimated_time,
                    'resource_link': resource_link,
                    'is_mandatory': is_mandatory
                }

                # Add quiz-specific fields if this is a quiz
                if task_type == 'quiz':
                    update_data.update({
                        'quiz_data': quiz_data_json,  # This is now a JSON string
                        'passing_score': quiz_data['settings']['passing_score'],
                        'max_attempts': quiz_data['settings']['max_attempts'],
                        'time_limit': quiz_data['settings']['time_limit'],
                        'question_order': quiz_data['settings']['question_order'],
                        'quiz_instructions': quiz_data['settings']['instructions']
                    })

                # Add assignment-specific fields if this is an assignment
                elif task_type == 'assignment':
                    update_data.update({
                        'assignment_instructions': assignment_instructions,
                        'due_date': due_date,
                        'max_file_size': max_file_size,
                        'allow_late_submissions': allow_late_submissions
                    })

                # Add reading-specific fields if this is a reading task
                elif task_type == 'reading':
                    update_data.update({
                        'reading_instructions': reading_instructions
                    })

                # Add discussion-specific fields if this is a discussion task
                elif task_type == 'discussion':
                    update_data.update({
                        'discussion_prompt': discussion_prompt,
                        'min_posts_required': min_posts_required,
                        'discussion_duration_days': discussion_duration_days,
                        'require_replies': require_replies
                    })

                print(f"DEBUG: Updating task with data: {update_data}")
                result = supabase.table('tasks').update(update_data).eq('id', task_id).execute()
                print(f"DEBUG: Update result: {result}")

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Task "{title}" updated successfully!', 'success')
                return redirect(url_for('admin_module_tasks', module_id=module['id']))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    pass
                flash(f'Error updating task: {str(e)}', 'error')
                return render_template('admin_edit_task.html',
                                     task=task,
                                     module=module,
                                     course=course,
                                     username=session.get('username'))

        return render_template('admin_edit_task.html',
                             task=task,
                             module=module,
                             course=course,
                             existing_questions=existing_questions,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/modules/<module_id>/tasks/add', methods=['GET', 'POST'])
@admin_required
def admin_add_task(module_id):
    try:
        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            task_type = request.form.get('type')
            order_index = request.form.get('order_index', 1)
            estimated_time = request.form.get('estimated_time', '30 minutes')
            resource_link = request.form.get('resource_link', '')
            is_mandatory = request.form.get('is_mandatory') == 'on'

            # Initialize task-specific variables with defaults
            quiz_data = ''
            passing_score = 70
            max_attempts = 3
            time_limit = 0
            question_order = 'sequential'
            quiz_instructions = ''
            assignment_instructions = ''
            due_date = None
            max_file_size = 10
            allow_late_submissions = False
            reading_instructions = ''
            discussion_prompt = ''
            min_posts_required = 1
            discussion_duration_days = 7
            require_replies = False

            # Handle quiz-specific settings
        
            # Handle assignment-specific settings
            if task_type == 'assignment':
                assignment_instructions = request.form.get('assignment_instructions', '')
                due_date = request.form.get('due_date')
                max_file_size = int(request.form.get('max_file_size', 10))
                allow_late_submissions = request.form.get('allow_late_submissions') == 'on'

                # Use assignment_instructions for task description
                description = f'Assignment: {assignment_instructions[:100]}...' if assignment_instructions else 'Assignment submission required'

            # Handle reading-specific settings
            elif task_type == 'reading':
                reading_instructions = request.form.get('reading_instructions', '')

            # Handle discussion-specific settings
            elif task_type == 'discussion':
                discussion_prompt = request.form.get('discussion_prompt', '')
                min_posts_required = int(request.form.get('min_posts_required', 1))
                discussion_duration_days = request.form.get('discussion_duration_days', '7')
                require_replies = request.form.get('require_replies') == 'on'

            # Validate required fields
            if not all([title, description, task_type]):
                flash('Title, description, and type are required.', 'error')
                return render_template('admin_add_task.html',
                                     module=module,
                                     course=course,
                                     username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Prepare task data
                task_data = {
                    'module_id': module_id,
                    'title': title,
                    'description': description,
                    'type': task_type,
                    'order_index': int(order_index),
                    'estimated_time': estimated_time,
                    'resource_link': resource_link,
                    'is_mandatory': is_mandatory
                }

                # Add quiz-specific fields if this is a quiz
                

                # Add assignment-specific fields if this is an assignment
                if task_type == 'assignment':
                    task_data.update({
                        'assignment_instructions': assignment_instructions,
                        'due_date': due_date,
                        'max_file_size': max_file_size,
                        'allow_late_submissions': allow_late_submissions
                    })

                # Add reading-specific fields if this is a reading task
                elif task_type == 'reading':
                    task_data.update({
                        'reading_instructions': reading_instructions
                    })

                # Add discussion-specific fields if this is a discussion task
                elif task_type == 'discussion':
                    task_data.update({
                        'discussion_prompt': discussion_prompt,
                        'min_posts_required': min_posts_required,
                        'discussion_duration_days': discussion_duration_days,
                        'require_replies': require_replies
                    })

                # Insert new test
                supabase.table('tests').insert(test_data).execute()

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Test "{title}" added successfully!', 'success')
                return redirect(url_for('admin_module_tests', module_id=module_id))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    pass
                flash(f'Error creating task: {str(e)}', 'error')
                return render_template('admin_add_task.html',
                                     module=module,
                                     course=course,
                                     username=session.get('username'))

        return render_template('admin_add_task.html',
                             module=module,
                             course=course,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def admin_add_user():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'student')

        # Validate required fields
        if not all([name, email, password]):
            flash('Name, email, and password are required.', 'error')
            return render_template('admin_add_user.html',
                                 username=session.get('username'))

        # Check if email is already taken
        existing_user = supabase.table('profiles').select('id').filter('email', 'eq', email).execute()
        if existing_user.data:
            flash('Email is already registered.', 'error')
            return render_template('admin_add_user.html',
                                 username=session.get('username'))

        # Hash password and create user
        password_hash = generate_password_hash(password)

        try:
            # Insert new user
            result = supabase.table('profiles').insert({
                'name': name,
                'email': email,
                'password_hash': password_hash,
                'role': role
            }).execute()

            flash(f'User "{name}" created successfully!', 'success')
            return redirect(url_for('admin_users'))

        except Exception as e:
            flash(f'Error creating user: {str(e)}', 'error')
            return render_template('admin_add_user.html',
                                 username=session.get('username'))

    # For GET requests, show the form
    return render_template('admin_add_user.html',
                         username=session.get('username'))

@app.route('/task/<task_id>/submit', methods=['GET', 'POST'])
@login_required
def submit_assignment(task_id):
    try:
        user_id = session.get('user_id')

        # Get task details
        task_result = supabase.table('tasks').select('*').filter('id', 'eq', task_id).execute()
        if not task_result.data:
            flash('Task not found.', 'error')
            return redirect(url_for('courses'))

        task = task_result.data[0]

        # Check if this is an assignment task
        if task['type'] != 'assignment':
            flash('This task does not accept file submissions.', 'error')
            return redirect(url_for('courses'))

        # Check if user is enrolled in the course
        course_id = None
        module_result = supabase.table('modules').select('course_id').filter('id', 'eq', task['module_id']).execute()
        if module_result.data:
            course_id = module_result.data[0]['course_id']

        if course_id:
            enrolled_result = supabase.table('enrollments').select('id').filter('student_id', 'eq', user_id).filter('course_id', 'eq', course_id).filter('status', 'eq', 'active').execute()
            if not enrolled_result.data:
                flash('You must be enrolled in this course to submit assignments.', 'error')
                return redirect(url_for('courses'))

        # Check if user already submitted this assignment
        existing_submission = supabase.table('submissions').select('*').filter('student_id', 'eq', user_id).filter('task_id', 'eq', task_id).execute()
        submission = existing_submission.data[0] if existing_submission.data else None

        if request.method == 'POST':
            # Handle file upload
            if 'file' not in request.files:
                flash('No file selected.', 'error')
                return redirect(request.url)

            file = request.files['file']
            if file.filename == '':
                flash('No file selected.', 'error')
                return redirect(request.url)

            # Validate file size
            max_size = task.get('max_file_size', 10) * 1024 * 1024  # Convert MB to bytes
            if len(file.read()) > max_size:
                flash(f'File size exceeds maximum allowed size of {task.get("max_file_size", 10)}MB.', 'error')
                return redirect(request.url)

            # Reset file pointer
            file.seek(0)

            # Validate file type (basic check)
            allowed_extensions = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'jpg', 'jpeg', 'png', 'gif']
            if '.' not in file.filename or file.filename.split('.')[-1].lower() not in allowed_extensions:
                flash('File type not allowed. Please upload PDF, Word document, text file, or image.', 'error')
                return redirect(request.url)

            try:
                # Upload file to Supabase storage
                bucket_name = 'student-submissions'
                file_path = f"{user_id}/{task_id}/{file.filename}"

                # Read file content as bytes for Supabase storage
                file_content = file.read()

                # Upload file
                upload_result = supabase.storage.from_(bucket_name).upload(file_path, file_content)

                if upload_result:
                    # Get public URL
                    file_url = supabase.storage.from_(bucket_name).get_public_url(file_path)

                    # Reset file pointer for size calculation
                    file.seek(0)
                    file_size = len(file.read())

                    # Save submission record
                    submission_data = {
                        'student_id': user_id,
                        'task_id': task_id,
                        'file_url': file_url,
                        'file_name': file.filename,
                        'file_size': file_size,
                        'file_type': file.content_type,
                        'status': 'submitted'
                    }

                    if submission:
                        # Update existing submission
                        supabase.table('submissions').update(submission_data).eq('id', submission['id']).execute()
                        flash('Assignment updated successfully!', 'success')
                    else:
                        # Create new submission
                        supabase.table('submissions').insert(submission_data).execute()
                        flash('Assignment submitted successfully!', 'success')

                    return redirect(url_for('my_submissions'))

                else:
                    flash('Error uploading file. Please try again.', 'error')

            except Exception as e:
                flash(f'Error submitting assignment: {str(e)}', 'error')

        # Get course and module info for display
        module = {}
        course = {}

        if task['module_id']:
            module_result = supabase.table('modules').select('*').filter('id', 'eq', task['module_id']).execute()
            if module_result.data:
                module = module_result.data[0]
                if module.get('course_id'):
                    course_result = supabase.table('courses').select('*').filter('id', 'eq', module['course_id']).execute()
                    if course_result.data:
                        course = course_result.data[0]

        return render_template('submit_assignment.html',
                             task=task,
                             module=module,
                             course=course,
                             submission=submission,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('courses'))


@app.route('/my-submissions')
@login_required
def my_submissions():
    try:
        user_id = session.get('user_id')

        # Get all submissions for current user
        submissions_result = supabase.table('submissions').select('*').filter('student_id', 'eq', user_id).order('submitted_at', desc=True).execute()
        submissions = submissions_result.data if submissions_result.data else []

        # Get task and course info for each submission
        for submission in submissions:
            # Get task info
            task_result = supabase.table('tasks').select('*').filter('id', 'eq', submission['task_id']).execute()
            if task_result.data:
                submission['task'] = task_result.data[0]

                # Get module info
                module_result = supabase.table('modules').select('*').filter('id', 'eq', submission['task']['module_id']).execute()
                if module_result.data:
                    submission['module'] = module_result.data[0]

                    # Get course info
                    course_result = supabase.table('courses').select('*').filter('id', 'eq', submission['module']['course_id']).execute()
                    if course_result.data:
                        submission['course'] = course_result.data[0]
            else:
                submission['task'] = {'title': 'Unknown Task'}
                submission['module'] = {'title': 'Unknown Module'}
                submission['course'] = {'title': 'Unknown Course'}

        return render_template('my_submissions.html',
                             submissions=submissions,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/admin/progress')
@admin_required
def admin_progress():
    try:
        # Get all students
        students_result = supabase.table('profiles').select('*').eq('role', 'student').execute()
        students = students_result.data if students_result.data else []

        # Get all courses for reference
        courses_result = supabase.table('courses').select('id, title').execute()
        courses_dict = {c['id']: c['title'] for c in courses_result.data} if courses_result.data else {}

        # Get enrollment and progress data for each student
        students_data = []
        course_metrics = {}
        
        # Initialize course metrics
        for course_id in courses_dict:
            course_metrics[course_id] = {
                'title': courses_dict[course_id],
                'total_students': 0,
                'avg_progress': 0,
                'completion_count': 0,
                'total_quizzes': 0,
                'avg_quiz_score': 0
            }

        for student in students:
            student_id = student['id']

            # Get enrollments with course details
            enrollments_result = (supabase.table('enrollments')
                               .select('course_id, status, progress_percentage, completed_at')
                               .eq('student_id', student_id)
                               .execute())
            enrollments = enrollments_result.data if enrollments_result.data else []

            # Get completed tasks and quiz attempts
            completed_tasks_result = (supabase.table('progress')
                                   .select('task_id, status, score')
                                   .eq('student_id', student_id)
                                   .eq('status', 'completed')
                                   .execute())
            
            completed_tasks = completed_tasks_result.data if completed_tasks_result.data else []
            
            # Get quiz attempts
            quiz_attempts_result = (supabase.table('quiz_attempts')
                                 .select('task_id, score, passed')
                                 .eq('student_id', student_id)
                                 .execute())
            quiz_attempts = quiz_attempts_result.data if quiz_attempts_result.data else []

            # Calculate course-specific metrics
            student_courses = {}
            for enrollment in enrollments:
                course_id = enrollment['course_id']
                if course_id not in student_courses:
                    student_courses[course_id] = {
                        'progress': enrollment['progress_percentage'] or 0,
                        'completed': 1 if enrollment['status'] == 'completed' else 0,
                        'quiz_scores': []
                    }
                    
                    # Update course metrics
                    if course_id in course_metrics:
                        course_metrics[course_id]['total_students'] += 1
                        course_metrics[course_id]['completion_count'] += (1 if enrollment['status'] == 'completed' else 0)

            # Process quiz attempts
            for attempt in quiz_attempts:
                # Find which course this quiz belongs to
                task_result = (supabase.table('tasks')
                            .select('module_id')
                            .eq('id', attempt['task_id'])
                            .execute())
                
                if task_result.data:
                    module_id = task_result.data[0]['module_id']
                    module_result = (supabase.table('modules')
                                  .select('course_id')
                                  .eq('id', module_id)
                                  .execute())
                    
                    if module_result.data:
                        course_id = module_result.data[0]['course_id']
                        if course_id in student_courses:
                            student_courses[course_id]['quiz_scores'].append(attempt['score'])
                            
                            # Update course metrics
                            if course_id in course_metrics:
                                course_metrics[course_id]['total_quizzes'] += 1
                                course_metrics[course_id]['avg_quiz_score'] = (
                                    (course_metrics[course_id]['avg_quiz_score'] * (course_metrics[course_id]['total_quizzes'] - 1) + attempt['score']) / 
                                    course_metrics[course_id]['total_quizzes']
                                )

            # Calculate overall metrics for the student
            total_tasks = 0
            for course_id, data in student_courses.items():
                # Get total tasks for this course
                modules_result = (supabase.table('modules')
                               .select('id')
                               .eq('course_id', course_id)
                               .execute())
                
                if modules_result.data:
                    module_ids = [m['id'] for m in modules_result.data]
                    tasks_result = (supabase.table('tasks')
                                 .select('id')
                                 .in_('module_id', module_ids)
                                 .execute())
                    
                    course_task_count = len(tasks_result.data) if tasks_result.data else 0
                    total_tasks += course_task_count

            students_data.append({
                'id': student['id'],
                'name': student['name'],
                'email': student['email'],
                'enrollments': enrollments,
                'completed_tasks': len(completed_tasks),
                'total_tasks': total_tasks,
                'overall_progress': round((len(completed_tasks) / total_tasks * 100), 1) if total_tasks > 0 else 0,
                'courses': student_courses,
                'quiz_attempts': quiz_attempts
            })

        # Calculate summary statistics
        total_enrollments = sum(len(student['enrollments']) for student in students_data)
        avg_progress = round(sum((student.get('overall_progress') or 0) for student in students_data) / len(students_data), 1) if students_data else 0
        completion_rate = len([s for s in students_data if (s.get('overall_progress') or 0) > 80])

        # Update course metrics with final calculations
        for course_id, metrics in course_metrics.items():
            if metrics['total_students'] > 0:
                metrics['completion_rate'] = round((metrics['completion_count'] / metrics['total_students']) * 100, 1)
            else:
                metrics['completion_rate'] = 0

        return render_template('admin_progress.html',
                             students=students_data,
                             courses=course_metrics,
                             total_enrollments=total_enrollments,
                             avg_progress=avg_progress,
                             completion_rate=completion_rate,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/course/<course_id>/analytics')
@admin_required
def course_analytics(course_id):
    try:
        # Get course details
        course_result = supabase.table('courses').select('*').eq('id', course_id).execute()
        if not course_result.data:
            flash('Course not found', 'error')
            return redirect(url_for('admin_progress'))
        
        course = course_result.data[0]
        
        # Get all modules for this course
        modules_result = (supabase.table('modules')
                        .select('id, title, order_index')
                        .eq('course_id', course_id)
                        .order('order_index')
                        .execute())
        
        modules = modules_result.data if modules_result.data else []
        
        # Get all students enrolled in this course
        enrollments_result = (supabase.table('enrollments')
                            .select('student_id, progress_percentage, status, enrolled_at')
                            .eq('course_id', course_id)
                            .execute())
        
        student_ids = [e['student_id'] for e in enrollments_result.data] if enrollments_result.data else []
        
        # Get student details with comprehensive progress data
        students_data = []
        if student_ids:
            students_result = (supabase.table('profiles')
                            .select('id, name, email')
                            .in_('id', student_ids)
                            .execute())
            
            students = {s['id']: s for s in students_result.data} if students_result.data else {}

            # Get tasks for each module
            module_tasks = {}
            for module in modules:
                module_id = module['id']
                tasks_result = supabase.table('tasks').select('id, title, type').eq('module_id', module_id).execute()
                module_tasks[module_id] = tasks_result.data if tasks_result.data else []

            # Get comprehensive progress for each student
            for enrollment in enrollments_result.data:
                student_id = enrollment['student_id']
                if student_id not in students:
                    continue

                student = students[student_id]

                # Initialize progress data
                progress_data = {
                    'completed_modules': 0,
                    'total_modules': len(modules),
                    'completed_tasks': 0,
                    'total_tasks': sum(len(tasks) for tasks in module_tasks.values()),
                    'quiz_attempts': 0,
                    'quiz_scores': [],
                    'assessments': [],
                    'module_progress': {}
                }

                # Get completed tasks
                if module_tasks:
                    all_task_ids = [task['id'] for tasks in module_tasks.values() for task in tasks]
                    if all_task_ids:
                        completed_tasks_result = (supabase.table('progress')
                                               .select('task_id, status')
                                               .eq('student_id', student_id)
                                               .in_('task_id', all_task_ids)
                                               .eq('status', 'completed')
                                               .execute())
                        progress_data['completed_tasks'] = len(completed_tasks_result.data) if completed_tasks_result.data else 0

                        # Calculate module completion
                        for module_id, tasks in module_tasks.items():
                            module_task_ids = [task['id'] for task in tasks]
                            if module_task_ids:
                                module_completed = (supabase.table('progress')
                                                  .select('task_id')
                                                  .eq('student_id', student_id)
                                                  .in_('task_id', module_task_ids)
                                                  .eq('status', 'completed')
                                                  .execute())
                                completed_count = len(module_completed.data) if module_completed.data else 0
                                progress_data['module_progress'][module_id] = {
                                    'completed': completed_count,
                                    'total': len(module_task_ids),
                                    'progress': round((completed_count / len(module_task_ids)) * 100, 1) if module_task_ids else 0
                                }

                # Get quiz attempts
                quiz_attempts_result = (supabase.table('quiz_attempts')
                                     .select('task_id, score, passed')
                                     .eq('student_id', student_id)
                                     .execute())
                if quiz_attempts_result.data:
                    progress_data['quiz_attempts'] = len(quiz_attempts_result.data)
                    progress_data['quiz_scores'] = [attempt['score'] for attempt in quiz_attempts_result.data if attempt['score']]

                # Get submissions (assessments)
                submissions_result = (supabase.table('submissions')
                                   .select('*')
                                   .eq('student_id', student_id)
                                   .execute())
                if submissions_result.data:
                    progress_data['assessments'] = submissions_result.data

                # Calculate completion percentage
                completion_percentage = 0
                if progress_data['total_tasks'] > 0:
                    completion_percentage = (progress_data['completed_tasks'] / progress_data['total_tasks']) * 100

                students_data.append({
                    'id': student['id'],
                    'name': student['name'],
                    'email': student['email'],
                    'progress': enrollment['progress_percentage'],
                    'status': enrollment['status'],
                    'enrolled_at': enrollment['enrolled_at'],
                    'detailed_progress': progress_data,
                    'module_progress': progress_data['module_progress'],
                    'completion_percentage': round(completion_percentage, 1),
                    'completed_quizzes': progress_data['quiz_attempts'],
                    'avg_quiz_score': round(sum(progress_data['quiz_scores']) / len(progress_data['quiz_scores']), 1) if progress_data['quiz_scores'] else 0,
                    'last_active': 'Recently'  # Placeholder for now
                })
        
        # Calculate overall course statistics
        total_students = len(students_data)
        avg_course_progress = round(sum(s['progress'] for s in students_data) / total_students, 1) if students_data else 0
        completion_rate = len([s for s in students_data if s['progress'] >= 80]) / total_students * 100 if total_students > 0 else 0
        
        # Get module completion statistics
        module_stats = []
        for module in modules:
            completed_count = sum(1 for s in students_data 
                               if module['id'] in s['module_progress'] and 
                               s['module_progress'][module['id']]['progress'] >= 80)
            
            # Calculate average quiz score for this module
            # Simplified for now - will be enhanced later
            avg_score = 0
            
            module_stats.append({
                'id': module['id'],
                'title': module['title'],
                'completion_rate': round((completed_count / total_students) * 100, 1) if total_students > 0 else 0,
                'completed': completed_count,
                'avg_score': avg_score,
                'order_index': module['order_index']
            })
        
        # Sort modules by order_index
        module_stats.sort(key=lambda x: x['order_index'])
        
        # Prepare data for charts
        progress_distribution = {}
        for student in students_data:
            progress_band = (student['progress'] // 10) * 10
            progress_distribution[progress_band] = progress_distribution.get(progress_band, 0) + 1
        
        # Get all submissions for students in this course
        all_submissions = []
        for student in students_data:
            student_submissions = student['detailed_progress']['assessments']
            for submission in student_submissions:
                # Get task and module info for this submission
                task_result = supabase.table('tasks').select('title, module_id').eq('id', submission['task_id']).execute()
                if task_result.data:
                    task = task_result.data[0]
                    module_result = supabase.table('modules').select('title').eq('id', task['module_id']).execute()
                    module_title = module_result.data[0]['title'] if module_result.data else 'Unknown Module'

                    all_submissions.append({
                        'id': submission['id'],
                        'student_id': student['id'],
                        'student_name': student['name'],
                        'student_email': student['email'],
                        'task_title': task['title'],
                        'module_title': module_title,
                        'submitted_at': submission['submitted_at'],
                        'file_name': submission.get('file_name', ''),
                        'file_url': submission.get('file_url', ''),
                        'grade': submission.get('grade'),
                        'feedback': submission.get('feedback', ''),
                        'status': submission.get('status', 'submitted')
                    })

        return render_template('course_analytics.html',
                             course=course,
                             modules=modules,
                             students=students_data,
                             submissions=all_submissions,
                             module_stats=module_stats,
                             total_students=total_students,
                             avg_course_progress=avg_course_progress,
                             completion_rate=round(completion_rate, 1),
                             progress_distribution=progress_distribution,
                             username=session.get('username'))
    
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin_progress'))
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/grade-submission/<submission_id>', methods=['GET', 'POST'])
@admin_required
def admin_grade_submission(submission_id):
    try:
        # Get submission details
        submission_result = supabase.table('submissions').select('*').eq('id', submission_id).execute()
        if not submission_result.data:
            flash('Submission not found', 'error')
            return redirect(url_for('admin_progress'))

        submission = submission_result.data[0]

        # Get student details
        student_result = supabase.table('profiles').select('id, name, email').eq('id', submission['student_id']).execute()
        student = student_result.data[0] if student_result.data else {'name': 'Unknown', 'email': 'unknown'}

        # Get task details
        task_result = supabase.table('tasks').select('id, title, module_id').eq('id', submission['task_id']).execute()
        task = task_result.data[0] if task_result.data else {'title': 'Unknown Task'}

        # Get module and course details
        if task.get('module_id'):
            module_result = supabase.table('modules').select('id, title, course_id').eq('id', task['module_id']).execute()
            module = module_result.data[0] if module_result.data else {'title': 'Unknown Module'}

            course_result = supabase.table('courses').select('id, title').eq('id', module.get('course_id')).execute()
            course = course_result.data[0] if course_result.data else {'title': 'Unknown Course'}
        else:
            module = {'title': 'Unknown Module'}
            course = {'title': 'Unknown Course'}

        if request.method == 'POST':
            grade = request.form.get('grade')
            feedback = request.form.get('feedback')

            if not grade:
                flash('Grade is required', 'error')
                return render_template('admin_grade_submission.html',
                                     submission=submission,
                                     student=student,
                                     task=task,
                                     module=module,
                                     course=course)

            try:
                grade_float = float(grade)
                if grade_float < 0 or grade_float > 100:
                    flash('Grade must be between 0 and 100', 'error')
                    return render_template('admin_grade_submission.html',
                                         submission=submission,
                                         student=student,
                                         task=task,
                                         module=module,
                                         course=course)
            except ValueError:
                flash('Invalid grade format', 'error')
                return render_template('admin_grade_submission.html',
                                     submission=submission,
                                     student=student,
                                     task=task,
                                     module=module,
                                     course=course)

            # Update submission with grade and feedback
            update_data = {
                'grade': grade_float,
                'feedback': feedback,
                'status': 'graded'
            }

            supabase.table('submissions').update(update_data).eq('id', submission_id).execute()

            flash(f'Assignment graded successfully! Grade: {grade_float}%', 'success')
            return redirect(url_for('course_analytics', course_id=course.get('id', '')))

        return render_template('admin_grade_submission.html',
                             submission=submission,
                             student=student,
                             task=task,
                             module=module,
                             course=course,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin_dashboard'))


@app.route('/student/grades')
@login_required
def student_grades():
    try:
        user_id = session.get('user_id')

        # Get all submissions for this student
        submissions_result = supabase.table('submissions').select('*').eq('student_id', user_id).execute()
        submissions = submissions_result.data if submissions_result.data else []

        # Get additional info for each submission
        submissions_with_details = []
        for submission in submissions:
            # Get task details
            task_result = supabase.table('tasks').select('title, module_id').eq('id', submission['task_id']).execute()
            task = task_result.data[0] if task_result.data else {'title': 'Unknown Task'}

            # Get module details
            if task.get('module_id'):
                module_result = supabase.table('modules').select('title, course_id').eq('id', task['module_id']).execute()
                module = module_result.data[0] if module_result.data else {'title': 'Unknown Module'}

                # Get course details
                if module.get('course_id'):
                    course_result = supabase.table('courses').select('title').eq('id', module['course_id']).execute()
                    course = course_result.data[0] if course_result.data else {'title': 'Unknown Course'}
                else:
                    course = {'title': 'Unknown Course'}
            else:
                module = {'title': 'Unknown Module'}
                course = {'title': 'Unknown Course'}

            submissions_with_details.append({
                'id': submission['id'],
                'task_title': task['title'],
                'module_title': module['title'],
                'course_title': course['title'],
                'submitted_at': submission['submitted_at'],
                'grade': submission.get('grade'),
                'feedback': submission.get('feedback', ''),
                'status': submission.get('status', 'submitted'),
                'file_name': submission.get('file_name', ''),
                'file_url': submission.get('file_url', '')
            })

        # Calculate overall statistics
        total_submissions = len(submissions_with_details)
        graded_submissions = len([s for s in submissions_with_details if s['grade'] is not None])
        avg_grade = 0
        if graded_submissions > 0:
            grades = [s['grade'] for s in submissions_with_details if s['grade'] is not None]
            avg_grade = round(sum(grades) / len(grades), 1)

        return render_template('student_grades.html',
                             submissions=submissions_with_details,
                             total_submissions=total_submissions,
                             graded_submissions=graded_submissions,
                             avg_grade=avg_grade,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        import traceback
        traceback.print_exc()
        return redirect(url_for('dashboard'))


@app.route('/admin/modules/<module_id>/tests/add', methods=['GET', 'POST'])
@admin_required
def admin_add_test(module_id):
    try:
        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            test_type = request.form.get('type', 'quiz')  # Default to 'quiz' type
            order_index = request.form.get('order_index', 1)
            time_limit = int(request.form.get('time_limit', 60))  # Default 60 minutes
            passing_score = int(request.form.get('passing_score', 70))  # Default 70%
            max_attempts = int(request.form.get('max_attempts', 1))  # Default 1 attempt
            is_mandatory = request.form.get('is_mandatory') == 'on'
            instructions = request.form.get('instructions', '')
            show_results = request.form.get('show_results') == 'on'
            
            # Validate required fields
            if not all([title, description, test_type]):
                flash('Title, description, and type are required.', 'error')
                return render_template('admin_add_test.html',
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Prepare test data
                test_data = {
                    'module_id': module_id,
                    'title': title,
                    'description': description,
                    'type': test_type,
                    'order_index': int(order_index),
                    'time_limit': time_limit,
                    'passing_score': passing_score,
                    'max_attempts': max_attempts,
                    'is_mandatory': is_mandatory,
                    'instructions': instructions,
                    'show_results': show_results,
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }

                # Insert new test
                supabase.table('tests').insert(test_data).execute()

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Test "{title}" added successfully!', 'success')
                return redirect(url_for('admin_module_tests', module_id=module_id))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    pass
                flash(f'Error creating test: {str(e)}', 'error')
                return render_template('admin_add_test.html',
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

        return render_template('admin_add_test.html',
                            module=module,
                            course=course,
                            username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))

@app.route('/admin/modules/<module_id>/tests')
@admin_required
def admin_module_tests(module_id):
    try:
        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        # Get all tests for this module
        tests_result = supabase.table('tests')\
            .select('*')\
            .eq('module_id', module_id)\
            .order('order_index')\
            .execute()

        tests = tests_result.data if hasattr(tests_result, 'data') else []

        return render_template('admin_module_tests.html',
                            module=module,
                            course=course,
                            tests=tests,
                            username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))

@app.route('/admin/tests/edit/<test_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_test(test_id):
    try:
        # Get test details
        test_result = supabase.table('tests').select('*').eq('id', test_id).execute()
        if not test_result.data:
            flash('Test not found.', 'error')
            return redirect(url_for('admin_courses'))

        test = test_result.data[0]
        
        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', test['module_id']).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            test_type = request.form.get('type', 'quiz')
            order_index = request.form.get('order_index', 1)
            time_limit = int(request.form.get('time_limit', 60))
            passing_score = int(request.form.get('passing_score', 70))
            max_attempts = int(request.form.get('max_attempts', 1))
            is_mandatory = request.form.get('is_mandatory') == 'on'
            instructions = request.form.get('instructions', '')
            show_results = request.form.get('show_results') == 'on'
            
            # Validate required fields
            if not all([title, description, test_type]):
                flash('Title, description, and type are required.', 'error')
                return render_template('admin_edit_test.html',
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Prepare test data
                update_data = {
                    'title': title,
                    'description': description,
                    'type': test_type,
                    'order_index': int(order_index),
                    'time_limit': time_limit,
                    'passing_score': passing_score,
                    'max_attempts': max_attempts,
                    'is_mandatory': is_mandatory,
                    'instructions': instructions,
                    'show_results': show_results
                }

                # Update the test
                supabase.table('tests').update(update_data).eq('id', test_id).execute()

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Test "{title}" updated successfully!', 'success')
                return redirect(url_for('admin_module_tests', module_id=module['id']))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except Exception as e:
                    pass
                flash(f'Error updating test: {str(e)}', 'error')
                return render_template('admin_edit_test.html',
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

        return render_template('admin_edit_test.html',
                            test=test,
                            module=module,
                            course=course,
                            username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))


@app.route('/admin/tests/<test_id>/manage', methods=['GET', 'POST'])
@admin_required
def admin_manage_test(test_id):
    try:
        # Get test details
        test_result = supabase.table('tests').select('*').eq('id', test_id).execute()
        if not test_result.data:
            flash('Test not found.', 'error')
            return redirect(url_for('admin_courses'))

        test = test_result.data[0]
        
        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', test['module_id']).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        # Get test questions
        questions_result = supabase.table('questions').select('*').eq('test_id', test_id).order('order_index').execute()
        questions = questions_result.data if hasattr(questions_result, 'data') else []

        # Get test statistics (placeholder - implement based on your needs)
        average_score = 78  # This would come from actual calculations
        completed_students = 42
        in_progress_students = 8
        not_started_students = 12
        
        # Calculate percentages
        total_students = completed_students + in_progress_students + not_started_students
        completed_percentage = (completed_students / total_students * 100) if total_students > 0 else 0
        in_progress_percentage = (in_progress_students / total_students * 100) if total_students > 0 else 0
        not_started_percentage = (not_started_students / total_students * 100) if total_students > 0 else 0

        return render_template('admin_manage_test.html',
                            test=test,
                            module=module,
                            course=course,
                            questions=questions,
                            average_score=average_score,
                            completed_students=completed_students,
                            in_progress_students=in_progress_students,
                            not_started_students=not_started_students,
                            completed_percentage=completed_percentage,
                            in_progress_percentage=in_progress_percentage,
                            not_started_percentage=not_started_percentage,
                            username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))

@app.route('/admin/tests/<test_id>/delete', methods=['POST'])
@admin_required
def admin_delete_test(test_id):
    try:
        # Get test details for confirmation
        test_result = supabase.table('tests').select('*').eq('id', test_id).execute()
        if not test_result.data:
            flash('Test not found.', 'error')
            return redirect(url_for('admin_courses'))

        test = test_result.data[0]
        
        # Temporarily disable RLS for admin operations
        supabase.rpc('disable_rls_for_admin', params={}).execute()
        
        # Delete test questions first (if they exist)
        supabase.table('questions').delete().eq('test_id', test_id).execute()
        
        # Delete the test
        supabase.table('tests').delete().eq('id', test_id).execute()
        
        # Re-enable RLS
        supabase.rpc('enable_rls_for_admin', params={}).execute()
        
        flash(f'Test "{test["title"]}" deleted successfully!', 'success')
        return redirect(url_for('admin_module_tests', module_id=test['module_id']))

    except Exception as e:
        # Make sure to re-enable RLS if there's an error
        try:
            supabase.rpc('enable_rls_for_admin', params={}).execute()
        except Exception as e:
            print(f"Error re-enabling RLS: {str(e)}")
        flash(f'Error deleting test: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))

@app.route('/admin/questions/add/<test_id>', methods=['GET', 'POST'])
@admin_required
def admin_add_question(test_id):
    try:
        # Get test details
        test_result = supabase.table('tests').select('*').eq('id', test_id).execute()
        if not test_result.data:
            flash('Test not found.', 'error')
            return redirect(url_for('admin_courses'))

        test = test_result.data[0]
        
        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', test['module_id']).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('admin_courses'))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', module['course_id']).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            question_text = request.form.get('question_text')
            question_type = request.form.get('question_type', 'multiple_choice')
            options = request.form.getlist('options[]')
            correct_answer = request.form.get('correct_answer')
            points = int(request.form.get('points', 1))
            
            # Validate required fields
            if not question_text:
                flash('Question text is required.', 'error')
                return render_template('admin_add_question.html',
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            # For multiple choice questions only
            if not options or len(options) < 2:
                flash('Multiple choice questions must have at least 2 options.', 'error')
                return render_template('admin_add_question.html',
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            if not correct_answer:
                flash('Please select the correct answer for this multiple choice question.', 'error')
                return render_template('admin_add_question.html',
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Get next order index
                questions_result = supabase.table('questions').select('order_index').eq('test_id', test_id).order('order_index', desc=True).execute()
                next_order = (questions_result.data[0]['order_index'] + 1) if questions_result.data else 1

                # Prepare question data
                question_data = {
                    'test_id': test_id,
                    'question_text': question_text,
                    'question_type': question_type,
                    'options': options,
                    'correct_answer': correct_answer,
                    'points': points,
                    'order_index': next_order
                }

                # Insert new question
                supabase.table('questions').insert(question_data).execute()

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Question added successfully!', 'success')
                return redirect(url_for('admin_manage_test', test_id=test_id))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    pass
                flash(f'Error creating question: {str(e)}', 'error')
                return render_template('admin_add_question.html',
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

        return render_template('admin_add_question.html',
                            test=test,
                            module=module,
                            course=course,
                            username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))

@app.route('/admin/questions/edit/<question_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_question(question_id):
    try:
        # Get question details
        question_result = supabase.table('questions').select('*').eq('id', question_id).execute()
        if not question_result.data:
            flash('Question not found.', 'error')
            return redirect(url_for('admin_courses'))

        question = question_result.data[0]
        
        # Get test, module and course details
        test_result = supabase.table('tests').select('*').eq('id', question['test_id']).execute()
        test = test_result.data[0] if test_result.data else {}
        
        module_result = supabase.table('modules').select('*').eq('id', test.get('module_id', '')).execute()
        module = module_result.data[0] if module_result.data else {}
        
        course_result = supabase.table('courses').select('*').eq('id', module.get('course_id', '')).execute()
        course = course_result.data[0] if course_result.data else {}

        if request.method == 'POST':
            question_text = request.form.get('question_text')
            question_type = request.form.get('question_type', 'multiple_choice')
            options = request.form.getlist('options[]')
            correct_answer = request.form.get('correct_answer')
            points = int(request.form.get('points', 1))
            
            # Validate required fields
            if not question_text:
                flash('Question text is required.', 'error')
                return render_template('admin_edit_question.html',
                                    question=question,
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            # For multiple choice questions only
            if not options or len(options) < 2:
                flash('Multiple choice questions must have at least 2 options.', 'error')
                return render_template('admin_edit_question.html',
                                    question=question,
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            if not correct_answer:
                flash('Please select the correct answer for this multiple choice question.', 'error')
                return render_template('admin_edit_question.html',
                                    question=question,
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

            try:
                # Temporarily disable RLS for admin operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Prepare question data
                update_data = {
                    'question_text': question_text,
                    'question_type': question_type,
                    'options': options,
                    'correct_answer': correct_answer,
                    'points': points
                }

                # Update the question
                supabase.table('questions').update(update_data).eq('id', question_id).execute()

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

                flash(f'Question updated successfully!', 'success')
                return redirect(url_for('admin_manage_test', test_id=test['id']))

            except Exception as e:
                # Make sure to re-enable RLS if there's an error
                try:
                    supabase.rpc('enable_rls_for_admin', params={}).execute()
                except:
                    pass
                flash(f'Error updating question: {str(e)}', 'error')
                return render_template('admin_edit_question.html',
                                    question=question,
                                    test=test,
                                    module=module,
                                    course=course,
                                    username=session.get('username'))

        return render_template('admin_edit_question.html',
                            question=question,
                            test=test,
                            module=module,
                            course=course,
                            username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))

@app.route('/admin/questions/delete/<question_id>', methods=['POST'])
@admin_required
def admin_delete_question(question_id):
    try:
        # Get question details
        question_result = supabase.table('questions').select('*').eq('id', question_id).execute()
        if not question_result.data:
            flash('Question not found.', 'error')
            return redirect(url_for('admin_courses'))

        question = question_result.data[0]
        test_id = question['test_id']
        
        # Temporarily disable RLS for admin operations
        supabase.rpc('disable_rls_for_admin', params={}).execute()
        
        # Delete the question
        supabase.table('questions').delete().eq('id', question_id).execute()
        
        # Re-enable RLS
        supabase.rpc('enable_rls_for_admin', params={}).execute()
        
        flash(f'Question deleted successfully!', 'success')
        return redirect(url_for('admin_manage_test', test_id=test_id))

    except Exception as e:
        # Make sure to re-enable RLS if there's an error
        try:
            supabase.rpc('enable_rls_for_admin', params={}).execute()
        except Exception as e:
            pass
        flash(f'Error deleting question: {str(e)}', 'error')
        return redirect(url_for('admin_courses'))



@app.route('/course/<course_id>/module/<module_id>/test/<test_id>')
@login_required
def course_test(course_id, module_id, test_id):
    try:
        user_id = session.get('user_id')

        # Get test details
        test_result = supabase.table('tests').select('*').eq('id', test_id).execute()
        if not test_result.data:
            flash('Test not found.', 'error')
            return redirect(url_for('course_modules', course_id=course_id))

        test = test_result.data[0]

        # Verify test belongs to the specified module
        if test['module_id'] != module_id:
            flash('Test not found in this module.', 'error')
            return redirect(url_for('course_modules', course_id=course_id))

        # Get module and course details
        module_result = supabase.table('modules').select('*').eq('id', module_id).execute()
        if not module_result.data:
            flash('Module not found.', 'error')
            return redirect(url_for('course_modules', course_id=course_id))

        module = module_result.data[0]
        course_result = supabase.table('courses').select('*').eq('id', course_id).execute()
        course = course_result.data[0] if course_result.data else {}

        # Check if user is enrolled in the course
        enrolled_result = supabase.table('enrollments').select('id').eq('student_id', user_id).eq('course_id', course_id).eq('status', 'active').execute()
        if not enrolled_result.data:
            flash('You must be enrolled in this course to take tests.', 'error')
            return redirect(url_for('courses'))

        # Get test questions
        questions_result = supabase.table('questions').select('*').eq('test_id', test_id).order('order_index').execute()
        questions = questions_result.data if hasattr(questions_result, 'data') else []

        # Find the quiz task for this module (assuming one quiz per module for now)
        task_result = supabase.table('tasks') \
            .select('id') \
            .eq('module_id', module_id) \
            .eq('type', 'quiz') \
            .execute()
            
        if not task_result.data:
            flash('No quiz task found for this module.', 'error')
            return redirect(url_for('course_modules', course_id=course_id))
            
        task_id = task_result.data[0]['id']

        # Check if user has already taken this test
        attempts_result = supabase.table('quiz_attempts') \
            .select('*') \
            .eq('student_id', user_id) \
            .eq('task_id', task_id) \
            .order('created_at', desc=True) \
            .execute()
        attempts = attempts_result.data if attempts_result.data else []

        # Check if user has reached max attempts
        if len(attempts) >= test['max_attempts']:
            flash(f'You have reached the maximum number of attempts ({test["max_attempts"]}) for this test.', 'error')
            return redirect(url_for('course_module_tasks', course_id=course_id, module_id=module_id))

        # Check if there's an in-progress attempt (not completed)
        in_progress_attempt = None
        for attempt in attempts:
            if not attempt.get('completed_at'):
                in_progress_attempt = attempt
                break

        # If no in-progress attempt, create one
        if not in_progress_attempt:
            try:
                # Temporarily disable RLS for test operations
                supabase.rpc('disable_rls_for_admin', params={}).execute()

                # Create new attempt with required fields from schema
                attempt_data = {
                    'student_id': user_id,
                    'task_id': task_id,
                    'course_id': course_id,
                    'module_id': module_id,
                    'score': 0,
                    'passed': False,
                    'answers': {},
                    'total_questions': len(questions),
                    'correct_answers': 0,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }

                attempt_result = supabase.table('quiz_attempts').insert(attempt_data).execute()
                if attempt_result.data:
                    in_progress_attempt = attempt_result.data[0]

                # Re-enable RLS
                supabase.rpc('enable_rls_for_admin', params={}).execute()

            except Exception as e:
                flash(f'Error starting test: {str(e)}', 'error')
                return redirect(url_for('course_modules', course_id=course_id))

        # Get user's current answers if they exist
        current_answers = in_progress_attempt.get('answers', {}) if in_progress_attempt else {}

        return render_template('course_test.html',
                             test=test,
                             module=module,
                             course=course,
                             questions=questions,
                             attempt=in_progress_attempt,
                             current_question=0,  # Start from first question
                             current_answers=current_answers,
                             username=session.get('username'))

    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('courses'))


@app.route('/course/<course_id>/module/<module_id>/test/<test_id>/submit', methods=['POST', 'OPTIONS'])
@login_required
def submit_quiz_attempt(course_id, module_id, test_id):
    user_id = session.get('user_id')
    if not user_id:
        response = jsonify({'success': False, 'message': 'User not authenticated.'})
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response, 401
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

    try:
        print(f"Starting quiz submission for test {test_id} by user {session.get('user_id')}")
        user_id = session.get('user_id')
        
        # Get JSON data with error handling
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Request must be JSON'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data received'}), 400
            
        print(f"Received data: {data}")
        
        # Find the quiz task for this module
        print(f"Looking for quiz task for module {module_id}")
        task_result = supabase.table('tasks') \
            .select('id') \
            .eq('module_id', module_id) \
            .eq('type', 'quiz') \
            .execute()
            
        if not task_result.data:
            print(f"No quiz task found for module {module_id}")
            return jsonify({'success': False, 'message': 'No quiz task found for this module'}), 404
            
        task_id = task_result.data[0]['id']
        print(f"Found quiz task ID: {task_id}")
        
        # Get the latest attempt for this user and task
        print(f"Looking for active quiz attempt for user {user_id} and task {task_id}")
        attempt_result = supabase.table('quiz_attempts') \
            .select('*') \
            .eq('student_id', user_id) \
            .eq('task_id', task_id) \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()
            
        if not attempt_result.data:
            print("No active quiz attempt found")
            return jsonify({'success': False, 'message': 'No active quiz attempt found'}), 400
            
        attempt = attempt_result.data[0]
        print(f"Found attempt: {attempt['id']}")
        
        # Update the attempt with the submitted answers
        update_data = {
            'answers': data.get('answers', {}),

            'updated_at': datetime.now().isoformat()
        }
        
        # Calculate score if all answers are submitted
        if 'answers' in data:
            print("Calculating score...")
            # Get the correct answers
            questions_result = supabase.table('questions') \
                .select('id, correct_answer') \
                .eq('test_id', test_id) \
                .execute()
                
            if not questions_result.data:
                print("No questions found for this test")
                return jsonify({'success': False, 'message': 'No questions found for this test'}), 400
                
            correct_answers = {str(q['id']): q['correct_answer'] for q in questions_result.data}
            print(f"Correct answers: {correct_answers}")
            
            # Calculate score
            correct_count = 0
            user_answers = data['answers']
            print(f"User answers: {user_answers}")
            
            for q_id, answer in user_answers.items():
                if q_id in correct_answers and answer == correct_answers[q_id]:
                    correct_count += 1
            
            total_questions = len(correct_answers)
            score = (correct_count / total_questions) * 100 if total_questions > 0 else 0
            
            update_data.update({
                'score': score,
                'correct_answers': correct_count,
                'total_questions': total_questions,
                'passed': score >= 70  # Assuming 70% is passing
            })
            
            print(f"Score calculated: {score}% ({correct_count}/{total_questions} correct)")
        
        # Mark the quiz task as completed in progress table
        try:
            # Check if progress record exists for this user and task
            progress_result = supabase.table('progress') \
                .select('*') \
                .eq('student_id', user_id) \
                .eq('task_id', task_id) \
                .execute()

            if progress_result.data:
                # Update existing progress record
                supabase.table('progress').update({
                    'status': 'completed' if update_data.get('passed', False) else 'in_progress',
                    'completion_percentage': update_data.get('score', 0),
                    'completed_at': datetime.now().isoformat() if update_data.get('passed', False) else None,
                    'updated_at': datetime.now().isoformat()
                }).eq('student_id', user_id).eq('task_id', task_id).execute()
            else:
                # Create new progress record
                supabase.table('progress').insert({
                    'student_id': user_id,
                    'task_id': task_id,
                    'course_id': course_id,
                    'module_id': module_id,
                    'status': 'completed' if update_data.get('passed', False) else 'in_progress',
                    'completion_percentage': update_data.get('score', 0),
                    'completed_at': datetime.now().isoformat() if update_data.get('passed', False) else None,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }).execute()

        except Exception as progress_error:
            print(f"Warning: Could not update progress table: {str(progress_error)}")
            # Don't fail the submission if progress update fails
        
        response = jsonify({
            'success': True,
            'score': update_data.get('score', 0),
            'passed': update_data.get('passed', False),
            'correct_answers': update_data.get('correct_answers', 0),
            'total_questions': update_data.get('total_questions', 0)
        })
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in submit_quiz_attempt: {str(e)}\n{error_trace}")
        response = jsonify({
            'success': False, 
            'message': 'An error occurred while processing your submission',
            'error': str(e),
            'trace': error_trace
        })
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response, 500


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
