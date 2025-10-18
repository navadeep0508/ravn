-- Drop existing policies first to avoid conflicts
DROP POLICY IF EXISTS "Users can view conversations they participate in" ON conversations;
DROP POLICY IF EXISTS "Users can create conversations" ON conversations;
DROP POLICY IF EXISTS "Users can view participants in their conversations" ON conversation_participants;
DROP POLICY IF EXISTS "Users can join conversations" ON conversation_participants;
DROP POLICY IF EXISTS "Users can view messages in their conversations" ON messages;
DROP POLICY IF EXISTS "Users can send messages to their conversations" ON messages;

-- Drop existing functions and triggers
DROP TRIGGER IF EXISTS trigger_update_conversation_last_message ON messages;
DROP TRIGGER IF EXISTS trigger_update_unread_counts ON messages;
DROP FUNCTION IF EXISTS update_conversation_last_message();
DROP FUNCTION IF EXISTS update_unread_counts();

-- Create conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE,
    created_by UUID REFERENCES profiles(id)
);

-- Create conversation participants table
CREATE TABLE IF NOT EXISTS conversation_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_read_at TIMESTAMP WITH TIME ZONE,
    unread_count INTEGER DEFAULT 0,
    UNIQUE(conversation_id, user_id)
);

-- Create messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'text', -- text, image, file, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    edited_at TIMESTAMP WITH TIME ZONE,
    is_deleted BOOLEAN DEFAULT FALSE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_conversation_id ON conversation_participants(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_user_id ON conversation_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for conversations
CREATE POLICY "Users can view conversations they participate in" ON conversations
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM conversation_participants cp
            WHERE cp.conversation_id = conversations.id
            AND cp.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can create conversations" ON conversations
    FOR INSERT WITH CHECK (created_by = auth.uid());

-- Create RLS policies for conversation participants
CREATE POLICY "Users can view participants in their conversations" ON conversation_participants
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM conversation_participants cp
            WHERE cp.conversation_id = conversation_participants.conversation_id
            AND cp.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can join conversations" ON conversation_participants
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- Create RLS policies for messages
CREATE POLICY "Users can view messages in their conversations" ON messages
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM conversation_participants cp
            WHERE cp.conversation_id = messages.conversation_id
            AND cp.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can send messages to their conversations" ON messages
    FOR INSERT WITH CHECK (sender_id = auth.uid());

-- Create function to update conversation last_message_at
CREATE OR REPLACE FUNCTION update_conversation_last_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations
    SET last_message_at = NOW(), updated_at = NOW()
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update conversation timestamp
CREATE TRIGGER trigger_update_conversation_last_message
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_last_message();

-- Create function to update unread counts
CREATE OR REPLACE FUNCTION update_unread_counts()
RETURNS TRIGGER AS $$
BEGIN
    -- Update unread counts for all participants except the sender
    UPDATE conversation_participants
    SET unread_count = unread_count + 1,
        last_read_at = CASE WHEN user_id = NEW.sender_id THEN last_read_at ELSE last_read_at END
    WHERE conversation_id = NEW.conversation_id
    AND user_id != NEW.sender_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update unread counts
CREATE TRIGGER trigger_update_unread_counts
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_unread_counts();
