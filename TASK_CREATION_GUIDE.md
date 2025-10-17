# Task Creation Guide for RAVN Learning Platform

## Overview
This guide explains how to create different types of tasks in your RAVN learning platform. Each task type serves a specific purpose in the learning experience.

## Task Types

### 🎥 Video Tasks
**Best for:** Video lectures, tutorials, and recorded content

**Features:**
- Automatic YouTube video embedding
- Responsive video player
- Auto-play option (configurable)

**Creation Steps:**
1. Select "Video" as task type
2. Enter a descriptive title
3. Provide YouTube URL (supports multiple formats)
4. Set estimated time and mandatory status

**Supported URL Formats:**
- `https://youtu.be/VIDEO_ID`
- `https://youtube.com/watch?v=VIDEO_ID`
- `https://youtube.com/embed/VIDEO_ID`

### 📖 Reading Tasks
**Best for:** Articles, documents, and text-based content

**Features:**
- Link to external resources (PDFs, web articles)
- Reading instructions for guidance
- Simple completion tracking

**Creation Steps:**
1. Select "Reading" as task type
2. Enter title and description
3. Provide reading material URL
4. Add specific reading instructions if needed

### ❓ Quiz Tasks
**Best for:** Knowledge assessment and testing

**Features:**
- Multiple choice questions
- Auto-grading and scoring
- Configurable passing scores and attempts

**Creation Steps:**
1. Select "Quiz" as task type
2. Enter quiz questions in specific format
3. Set passing score (default: 70%)
4. Configure max attempts (default: 3)

**Question Format:**
```
What is the capital of France?
A) London
B) Berlin
C) Paris
D) Madrid
Answer: C
```

### 📝 Assignment Tasks
**Best for:** Hands-on projects and homework

**Features:**
- File upload capability
- Due date setting
- Manual grading by instructors
- Late submission options

**Creation Steps:**
1. Select "Assignment" as task type
2. Provide detailed instructions
3. Set due date and file size limits
4. Configure late submission policy

### 💬 Discussion Tasks
**Best for:** Community interaction and peer learning

**Features:**
- Forum-style discussions
- Minimum participation requirements
- Time-limited or ongoing discussions

**Creation Steps:**
1. Select "Discussion" as task type
2. Create engaging discussion prompt
3. Set participation requirements
4. Configure discussion duration

## Best Practices

### Task Sequencing
1. **Start with foundational content** (Video/Reading tasks)
2. **Add interactive elements** (Quiz tasks for assessment)
3. **Include hands-on practice** (Assignment tasks)
4. **Encourage collaboration** (Discussion tasks)

### Task Design Tips
- **Keep tasks focused** - One clear learning objective per task
- **Provide clear instructions** - Students should know exactly what to do
- **Set appropriate time estimates** - Be realistic about completion time
- **Use mandatory flags wisely** - Only for essential learning outcomes

### Content Organization
- **Logical flow** - Tasks should build on each other
- **Progressive difficulty** - Start simple, increase complexity
- **Mixed task types** - Combine different types for engagement
- **Regular checkpoints** - Use quizzes to verify understanding

## Technical Notes

### Video Embedding
- Only YouTube URLs are currently supported
- Videos are automatically converted to embed format
- Responsive design works on all devices

### File Uploads (Assignments)
- Support for common file types (PDF, DOC, images)
- Configurable file size limits
- Secure file storage in Supabase

### Quiz System
- Simple text-based question format
- Auto-grading for objective questions
- Score tracking and attempt limiting

## Troubleshooting

### Common Issues
1. **Videos not playing** - Check YouTube URL format and video privacy settings
2. **Tasks not appearing** - Verify module and course relationships
3. **Progress not tracking** - Check database permissions and RLS policies

### Getting Help
- Check the browser console for JavaScript errors
- Verify database schema matches the application expectations
- Test with sample data before creating complex tasks

## Advanced Features (Future)

- Rich text editors for task descriptions
- Advanced quiz question types (drag-and-drop, matching)
- Peer grading for assignments
- Discussion analytics and moderation tools
- Task dependencies and prerequisites

---

*This guide will be updated as new features are added to the platform.*
