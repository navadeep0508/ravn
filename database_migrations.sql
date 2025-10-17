-- Migration: Create course structure tables
    -- Run this in Supabase SQL Editor

    -- Drop existing policies first to avoid dependency issues
    DROP POLICY IF EXISTS "Students can insert their own progress" ON progress;
    DROP POLICY IF EXISTS "Students can update their own progress" ON progress;
    DROP POLICY IF EXISTS "Students can view their own progress" ON progress;
    DROP POLICY IF EXISTS "Teachers can view progress in their courses" ON progress;
    DROP POLICY IF EXISTS "Teachers can manage their courses" ON courses;
    DROP POLICY IF EXISTS "Everyone can view courses" ON courses;
    DROP POLICY IF EXISTS "Teachers can manage modules in their courses" ON modules;
    DROP POLICY IF EXISTS "Everyone can view modules" ON modules;
    DROP POLICY IF EXISTS "Teachers can manage tasks in their courses" ON tasks;
    DROP POLICY IF EXISTS "Everyone can view tasks" ON tasks;
    DROP POLICY IF EXISTS "Students can manage their own progress" ON progress;
    DROP POLICY IF EXISTS "Teachers can view progress in their courses" ON progress;
    DROP POLICY IF EXISTS "Teachers can manage prerequisites in their courses" ON prerequisites;
    DROP POLICY IF EXISTS "Students can manage their own enrollments" ON enrollments;
    DROP POLICY IF EXISTS "Everyone can view enrollments" ON enrollments;

    -- Drop existing tables if they exist (to avoid conflicts on re-run)
    -- Note: Dropping enrollments first due to foreign key constraints
    DROP TABLE IF EXISTS enrollments CASCADE;
    DROP TABLE IF EXISTS prerequisites CASCADE;
    DROP TABLE IF EXISTS progress CASCADE;
    DROP TABLE IF EXISTS tasks CASCADE;
    DROP TABLE IF EXISTS modules CASCADE;
    DROP TABLE IF EXISTS courses CASCADE;

    -- Courses table (enhanced)
    CREATE TABLE IF NOT EXISTS courses (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        level TEXT NOT NULL CHECK (level IN ('Beginner', 'Intermediate', 'Advanced')),
        duration TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'English',
        thumbnail_url TEXT,
        intro_video_url TEXT,
        teacher_uuid UUID REFERENCES profiles(id),
        price DECIMAL(10,2) DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'draft')),
        start_date DATE,
        end_date DATE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Modules table
    CREATE TABLE IF NOT EXISTS modules (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT,
        order_index INTEGER NOT NULL,
        is_locked BOOLEAN DEFAULT false,
        due_date DATE,
        content_link TEXT,
        estimated_time TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Tasks table
    CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('video', 'quiz', 'reading', 'assignment', 'discussion')),
    title TEXT NOT NULL,
    description TEXT,
    resource_link TEXT,
    is_mandatory BOOLEAN DEFAULT true,
    order_index INTEGER NOT NULL,
    estimated_time TEXT,
    points INTEGER DEFAULT 0,
    -- Quiz-specific fields
    passing_score INTEGER DEFAULT 70,
    quiz_data TEXT,
    max_attempts INTEGER DEFAULT 3,
    -- Assignment-specific fields for tasks table
    assignment_instructions TEXT,
    due_date DATE,
    max_file_size INTEGER DEFAULT 10, -- in MB
    allow_late_submissions BOOLEAN DEFAULT false,

    -- Discussion-specific fields for tasks table
    discussion_prompt TEXT,
    min_posts_required INTEGER DEFAULT 1,
    discussion_duration_days INTEGER DEFAULT 7,
    require_replies BOOLEAN DEFAULT false,

    -- Reading-specific fields for tasks table
    reading_instructions TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
    CREATE TABLE IF NOT EXISTS progress (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID REFERENCES profiles(id) NOT NULL,
        course_id UUID REFERENCES courses(id) NOT NULL,
        module_id UUID REFERENCES modules(id) NOT NULL,
        task_id UUID REFERENCES tasks(id) NOT NULL,
        status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started', 'in_progress', 'completed')),
        completion_percentage DECIMAL(5,2) DEFAULT 0,
        completed_at TIMESTAMP WITH TIME ZONE,
        score DECIMAL(5,2),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(student_id, task_id)
    );
    CREATE TABLE IF NOT EXISTS submissions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID REFERENCES profiles(id) NOT NULL,
        task_id UUID REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,
        file_url TEXT NOT NULL, -- URL to file in Supabase storage
        file_name TEXT NOT NULL,
        file_size INTEGER, -- in bytes
        file_type TEXT, -- MIME type
        submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'graded', 'returned')),
        grade DECIMAL(5,2), -- percentage or points
        feedback TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(student_id, task_id)
    );
    -- We'll enable and configure it after confirming everything works
    ALTER TABLE progress DISABLE ROW LEVEL SECURITY;

    -- Prerequisites table for locking mechanism
    CREATE TABLE IF NOT EXISTS prerequisites (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
        prerequisite_module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
        unlock_condition TEXT DEFAULT 'completion',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Users table (for additional user data beyond auth.users)
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
        email TEXT UNIQUE NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Enrollments table for tracking user course enrollments
    CREATE TABLE IF NOT EXISTS enrollments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
        course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
        enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'dropped')),
        progress_percentage DECIMAL(5,2) DEFAULT 0,
        completed_at TIMESTAMP WITH TIME ZONE,
        UNIQUE(student_id, course_id)
    );

    -- Enable Row Level Security (RLS) on all tables except progress for now
    ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
    ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
    ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
    -- Temporarily disable RLS on progress table to fix the issue
    ALTER TABLE progress DISABLE ROW LEVEL SECURITY;
    ALTER TABLE users ENABLE ROW LEVEL SECURITY;
    ALTER TABLE prerequisites ENABLE ROW LEVEL SECURITY;
    ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY;
    ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;

    -- Drop existing policies if they exist (to avoid conflicts on re-run)
    DROP POLICY IF EXISTS "Teachers can manage their courses" ON courses;
    DROP POLICY IF EXISTS "Everyone can view courses" ON courses;
    DROP POLICY IF EXISTS "Teachers can manage modules in their courses" ON modules;
    DROP POLICY IF EXISTS "Everyone can view modules" ON modules;
    DROP POLICY IF EXISTS "Teachers can manage tasks in their courses" ON tasks;
    DROP POLICY IF EXISTS "Everyone can view tasks" ON tasks;
    -- Note: Progress table policies are removed since RLS is disabled
    DROP POLICY IF EXISTS "Teachers can manage prerequisites in their courses" ON prerequisites;
    DROP POLICY IF EXISTS "Students can manage their own submissions" ON submissions;
    DROP POLICY IF EXISTS "Teachers can view submissions in their courses" ON submissions;
    DROP POLICY IF EXISTS "Students can manage their own enrollments" ON enrollments;
    DROP POLICY IF EXISTS "Everyone can view enrollments" ON enrollments;

    -- RLS Policies for courses (teachers can manage their courses, students can view)
    CREATE POLICY "Teachers can manage their courses" ON courses
        FOR ALL USING (
            teacher_uuid = auth.uid() OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') OR
            auth.role() = 'service_role'
        );

    CREATE POLICY "Everyone can view courses" ON courses
        FOR SELECT USING (true);

    -- RLS Policies for modules
    CREATE POLICY "Teachers can manage modules in their courses" ON modules
        FOR ALL USING (
            EXISTS (SELECT 1 FROM courses WHERE id = course_id AND teacher_uuid = auth.uid()) OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') OR
            auth.role() = 'service_role'
        );

    CREATE POLICY "Everyone can view modules" ON modules
        FOR SELECT USING (true);

    -- RLS Policies for tasks
    CREATE POLICY "Teachers can manage tasks in their courses" ON tasks
        FOR ALL USING (
            EXISTS (SELECT 1 FROM modules m JOIN courses c ON m.course_id = c.id
                WHERE m.id = module_id AND c.teacher_uuid = auth.uid()) OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') OR
            auth.role() = 'service_role'
        );

    CREATE POLICY "Everyone can view tasks" ON tasks
        FOR SELECT USING (true);

    -- Note: RLS is disabled on the progress table, so no policies are needed
-- We'll add these back once we confirm everything is working

    -- RLS Policies for prerequisites
    CREATE POLICY "Teachers can manage prerequisites in their courses" ON prerequisites
        FOR ALL USING (
            EXISTS (SELECT 1 FROM modules m JOIN courses c ON m.course_id = c.id
                WHERE m.id IN (module_id, prerequisite_module_id) AND c.teacher_uuid = auth.uid()) OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') OR
            auth.role() = 'service_role'
        );

    -- RLS Policies for submissions (students can manage their own, teachers can view in their courses)
    CREATE POLICY "Students can manage their own submissions" ON submissions
        FOR ALL USING (
            student_id = auth.uid() OR
            auth.role() = 'service_role' OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
        );

    CREATE POLICY "Teachers can view submissions in their courses" ON submissions
        FOR SELECT USING (
            EXISTS (SELECT 1 FROM tasks t JOIN modules m ON t.module_id = m.id JOIN courses c ON m.course_id = c.id
                WHERE t.id = task_id AND c.teacher_uuid = auth.uid()) OR
            auth.role() = 'service_role' OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
        );

    -- RLS Policies for users (users can view and manage their own data)
    CREATE POLICY "Users can view and manage their own data" ON users
        FOR ALL USING (
            id = auth.uid() OR
            auth.role() = 'service_role' OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
        );

    -- RLS Policies for enrollments (students can manage their own enrollments)
    CREATE POLICY "Students can manage their own enrollments" ON enrollments
        FOR ALL USING (
            student_id = auth.uid() OR
            auth.jwt() ->> 'role' = 'service_role' OR
            EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
        );

    CREATE POLICY "Everyone can view enrollments" ON enrollments
        FOR SELECT USING (true);

    -- Functions for progress calculation
    CREATE OR REPLACE FUNCTION calculate_module_progress(student_uuid UUID, module_uuid UUID)
    RETURNS DECIMAL AS $$
    DECLARE
        total_tasks INTEGER;
        completed_tasks INTEGER;
        progress_percentage DECIMAL;
    BEGIN
        SELECT COUNT(*), COUNT(CASE WHEN status = 'completed' THEN 1 END)
        INTO total_tasks, completed_tasks
        FROM tasks t
        WHERE t.module_id = module_uuid;

        IF total_tasks = 0 THEN
            RETURN 0;
        END IF;

        progress_percentage := (completed_tasks::DECIMAL / total_tasks::DECIMAL) * 100;
        RETURN progress_percentage;
    END;
    $$ LANGUAGE plpgsql;

    CREATE OR REPLACE FUNCTION calculate_course_progress(student_uuid UUID, course_uuid UUID)
    RETURNS DECIMAL AS $$
    DECLARE
        total_modules INTEGER;
        completed_modules INTEGER;
        progress_percentage DECIMAL;
    BEGIN
        SELECT COUNT(*), COUNT(CASE WHEN progress >= 100 THEN 1 END)
        INTO total_modules, completed_modules
        FROM (
            SELECT m.id, calculate_module_progress(student_uuid, m.id) as progress
            FROM modules m
            WHERE m.course_id = course_uuid
        ) module_progress;

        IF total_modules = 0 THEN
            RETURN 0;
        END IF;

        progress_percentage := (completed_modules::DECIMAL / total_modules::DECIMAL) * 100;
        RETURN progress_percentage;
    END;
    $$ LANGUAGE plpgsql;

    -- Function to check if module should be unlocked
    CREATE OR REPLACE FUNCTION should_unlock_module(student_uuid UUID, module_uuid UUID)
    RETURNS BOOLEAN AS $$
    DECLARE
        prereq RECORD;
        module_completed BOOLEAN := false;
    BEGIN
        -- Check if all prerequisites are met
        FOR prereq IN
            SELECT prerequisite_module_id, unlock_condition
            FROM prerequisites
            WHERE module_id = module_uuid
        LOOP
            -- For now, assume unlock_condition = 'completion'
            SELECT calculate_module_progress(student_uuid, prereq.prerequisite_module_id) >= 100
            INTO module_completed;

            IF NOT module_completed THEN
                RETURN false;
            END IF;
        END LOOP;

        RETURN true;
    END;
    $$ LANGUAGE plpgsql;

    CREATE OR REPLACE FUNCTION get_teacher_student_count(teacher_id_param UUID)
    RETURNS INTEGER AS $$
    DECLARE
        student_count INTEGER;
    BEGIN
        SELECT COUNT(DISTINCT e.student_id)
        INTO student_count
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        WHERE c.teacher_uuid = teacher_id_param;

        RETURN student_count;
    END;
    $$ LANGUAGE plpgsql;

    CREATE OR REPLACE FUNCTION get_recent_submissions_for_teacher(teacher_id_param UUID)
    RETURNS TABLE (
        id UUID,
        student_id UUID,
        task_id UUID,
        file_url TEXT,
        file_name TEXT,
        submitted_at TIMESTAMP WITH TIME ZONE,
        status TEXT,
        grade DECIMAL,
        feedback TEXT,
        task_title TEXT,
        module_title TEXT,
        course_title TEXT,
        student_name TEXT
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT
            s.id,
            s.student_id,
            s.task_id,
            s.file_url,
            s.file_name,
            s.submitted_at,
            s.status,
            s.grade,
            s.feedback,
            t.title AS task_title,
            m.title AS module_id,
            c.title AS course_title,
            p.full_name AS student_name
        FROM submissions s
        JOIN tasks t ON s.task_id = t.id
        JOIN modules m ON t.module_id = m.id
        JOIN courses c ON m.course_id = c.id
        JOIN profiles p ON s.student_id = p.id
        WHERE c.teacher_uuid = teacher_id_param
        ORDER BY s.submitted_at DESC
        LIMIT 5;
    END;
    $$ LANGUAGE plpgsql;

    -- Functions for admin operations (temporarily disable RLS)
    CREATE OR REPLACE FUNCTION disable_rls_for_admin()
    RETURNS void AS $$
    BEGIN
        -- Disable RLS on tables for admin operations
        ALTER TABLE courses DISABLE ROW LEVEL SECURITY;
        ALTER TABLE modules DISABLE ROW LEVEL SECURITY;
        ALTER TABLE tasks DISABLE ROW LEVEL SECURITY;
        ALTER TABLE progress DISABLE ROW LEVEL SECURITY;
        ALTER TABLE prerequisites DISABLE ROW LEVEL SECURITY;
        ALTER TABLE enrollments DISABLE ROW LEVEL SECURITY;
        ALTER TABLE submissions DISABLE ROW LEVEL SECURITY;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;

    CREATE OR REPLACE FUNCTION enable_rls_for_admin()
    RETURNS void AS $$
    BEGIN
        -- Re-enable RLS on tables after admin operations
        ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
        ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
        ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
        ALTER TABLE progress ENABLE ROW LEVEL SECURITY;
        ALTER TABLE prerequisites ENABLE ROW LEVEL SECURITY;
        ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY;
        ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;

    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_courses_teacher ON courses(teacher_uuid);
    CREATE INDEX IF NOT EXISTS idx_modules_course ON modules(course_id);
    CREATE INDEX IF NOT EXISTS idx_modules_order ON modules(course_id, order_index);
    CREATE INDEX IF NOT EXISTS idx_tasks_module ON tasks(module_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_order ON tasks(module_id, order_index);
    CREATE INDEX IF NOT EXISTS idx_progress_student ON progress(student_id);
    CREATE INDEX IF NOT EXISTS idx_progress_course ON progress(course_id);
    CREATE INDEX IF NOT EXISTS idx_progress_module ON progress(module_id);
    CREATE INDEX IF NOT EXISTS idx_prerequisites_module ON prerequisites(module_id);
    CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
    CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);
    CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id);
    CREATE INDEX IF NOT EXISTS idx_submissions_task ON submissions(task_id);

    -- Temporarily disable RLS for sample data insertion
    ALTER TABLE courses DISABLE ROW LEVEL SECURITY;
    ALTER TABLE modules DISABLE ROW LEVEL SECURITY;
    ALTER TABLE tasks DISABLE ROW LEVEL SECURITY;
    ALTER TABLE progress DISABLE ROW LEVEL SECURITY;
    ALTER TABLE users DISABLE ROW LEVEL SECURITY;
    ALTER TABLE prerequisites DISABLE ROW LEVEL SECURITY;
    ALTER TABLE enrollments DISABLE ROW LEVEL SECURITY;
    ALTER TABLE submissions DISABLE ROW LEVEL SECURITY;

    -- Insert sample data for testing
    INSERT INTO courses (title, description, category, level, duration, language, teacher_uuid, price, status)
    SELECT
        'Python for Everybody',
        'Learn Python from basics to advanced topics with hands-on projects.',
        'Programming',
        'Beginner',
        '6 weeks',
        'English',
        p.id,
        0,
        'active'
    FROM profiles p
    WHERE p.role = 'teacher'
    LIMIT 1;

    -- Add sample modules to the course
    INSERT INTO modules (course_id, title, description, order_index, estimated_time)
    SELECT
        c.id,
        'Week 1: Introduction to Python',
        'Understand basic syntax and data types.',
        1,
        '3 hours'
    FROM courses c
    WHERE c.title = 'Python for Everybody';

    INSERT INTO modules (course_id, title, description, order_index, estimated_time)
    SELECT
        c.id,
        'Week 2: Control Structures',
        'Learn about if statements, loops, and functions.',
        2,
        '4 hours'
    FROM courses c
    WHERE c.title = 'Python for Everybody';

    -- Add sample tasks
    INSERT INTO tasks (module_id, type, title, description, order_index, estimated_time, is_mandatory)
    SELECT
        m.id,
        'video',
        'Welcome Video',
        'Introduction to the course and Python basics.',
        1,
        '15 minutes',
        true
    FROM modules m
    WHERE m.title = 'Week 1: Introduction to Python';

    INSERT INTO tasks (module_id, type, title, description, order_index, estimated_time, is_mandatory)
    SELECT
        m.id,
        'reading',
        'Python Basics Reading',
        'Read about Python syntax and data types.',
        2,
        '30 minutes',
        true
    FROM modules m
    WHERE m.title = 'Week 1: Introduction to Python';

    INSERT INTO tasks (module_id, type, title, description, order_index, estimated_time, is_mandatory)
    SELECT
        m.id,
        'quiz',
        'Python Basics Quiz',
        'Test your understanding of Python basics.',
        3,
        '20 minutes',
        true
    FROM modules m
    WHERE m.title = 'Week 1: Introduction to Python';

    -- Re-enable RLS after sample data insertion
    ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
    ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
    ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
    ALTER TABLE progress ENABLE ROW LEVEL SECURITY;
    ALTER TABLE users ENABLE ROW LEVEL SECURITY;
    ALTER TABLE prerequisites ENABLE ROW LEVEL SECURITY;
    ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY;
    ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
