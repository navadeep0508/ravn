-- Create quiz_attempts table
CREATE TABLE IF NOT EXISTS public.quiz_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    module_id UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    score FLOAT NOT NULL,
    passed BOOLEAN NOT NULL,
    answers JSONB NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_answers INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add RLS policies for quiz_attempts
ALTER TABLE public.quiz_attempts ENABLE ROW LEVEL SECURITY;

-- Allow students to view their own quiz attempts
CREATE POLICY "Allow users to view their own quiz attempts"
    ON public.quiz_attempts
    FOR SELECT
    USING (auth.uid() = student_id);

-- Allow students to create quiz attempts
CREATE POLICY "Allow users to create quiz attempts"
    ON public.quiz_attempts
    FOR INSERT
    WITH CHECK (auth.uid() = student_id);

-- Allow admins full access
CREATE POLICY "Enable all for admin users"
    ON public.quiz_attempts
    FOR ALL
    USING (EXISTS (
        SELECT 1 FROM profiles 
        WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
    ));
