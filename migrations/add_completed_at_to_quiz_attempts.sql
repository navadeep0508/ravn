-- Add completed_at column to quiz_attempts table
ALTER TABLE public.quiz_attempts 
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;

-- Update existing records to have completed_at set to updated_at
UPDATE public.quiz_attempts 
SET completed_at = updated_at 
WHERE completed_at IS NULL;
