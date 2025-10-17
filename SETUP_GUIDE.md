# Quick Setup Guide

## Step-by-Step Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

This will install:
- Flask (web framework)
- Werkzeug (password hashing)
- Supabase (database client)
- python-dotenv (environment variables)

### 2. Configure Environment
```bash
python setup_env.py
```

This creates a `.env` file with your Supabase credentials:
- SUPABASE_URL
- SUPABASE_KEY
- SECRET_KEY (auto-generated)

### 3. Run the Application
```bash
python app.py
```

The server will start on `http://localhost:5000`

## Testing the Application

### Create an Account
1. Go to `http://localhost:5000/signup`
2. Fill in:
   - Username: Your name
   - Email: Your email
   - Password: At least 6 characters
3. Click "Create Account"
4. User will be saved to Supabase with role='student'

### Login
1. Go to `http://localhost:5000/login`
2. Enter your email and password
3. Click "Sign In"
4. You'll be redirected to the dashboard

### Verify in Supabase
1. Go to your Supabase project dashboard
2. Navigate to Table Editor > profiles
3. You should see your user data with:
   - Auto-generated UUID
   - Your name and email
   - Hashed password
   - Role: 'student'
   - Timestamp

## Troubleshooting

### Import Errors
If you see import errors, make sure you've activated your virtual environment:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Supabase Connection Issues
- Check that `.env` file exists
- Verify SUPABASE_URL and SUPABASE_KEY are correct
- Ensure your Supabase project is active

### Database Errors
- Verify the `profiles` table exists in Supabase
- Check table structure matches:
  - id (uuid)
  - name (text)
  - email (text, unique)
  - password_hash (text)
  - role (text)
  - created_at (timestamp)

## What Happens on Signup

1. Form validation (client-side)
2. Password strength check
3. Server receives data
4. Checks if email already exists in Supabase
5. Hashes password with Werkzeug
6. Inserts new record into `profiles` table:
   ```python
   {
       'name': username,
       'email': email,
       'password_hash': hashed_password,
       'role': 'student'  # Automatically set
   }
   ```
7. Redirects to login page

## What Happens on Login

1. Server receives email and password
2. Queries Supabase for user with matching email
3. Verifies password hash
4. Creates session with:
   - user_id (UUID)
   - username
   - email
   - role
5. Redirects to dashboard

## Security Notes

✅ **Good Practices:**
- Passwords are hashed (never stored in plain text)
- Environment variables for sensitive data
- Session-based authentication
- .env file in .gitignore

⚠️ **To Add for Production:**
- Enable RLS on Supabase
- Add CSRF protection
- Implement rate limiting
- Add email verification
- Use HTTPS only
