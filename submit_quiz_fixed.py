@app.route('/course/<course_id>/module/<module_id>/task/<task_id>/submit_quiz', methods=['POST'])
@login_required
def submit_quiz(course_id, module_id, task_id):
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        user_id = session.get('user_id')
        user_email = session.get('user_email')
        full_name = session.get('full_name', '')
        
        if not user_id or not user_email:
            raise Exception("User not properly authenticated. Please log in again.")
        
        # Verify user is enrolled
        enrolled = supabase.table('enrollments') \
            .select('id') \
            .eq('student_id', user_id) \
            .eq('course_id', course_id) \
            .eq('status', 'active') \
            .execute()
            
        if not enrolled.data:
            error_msg = 'You are not enrolled in this course.'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg}), 403
            flash(error_msg, 'error')
            return redirect(url_for('course_detail', course_id=course_id))
        
        # Get the quiz data
        task_result = supabase.table('tasks').select('*').eq('id', task_id).execute()
        if not task_result.data:
            error_msg = 'Quiz not found.'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg}), 404
            flash(error_msg, 'error')
            return redirect(url_for('course_module_tasks', course_id=course_id, module_id=module_id))
            
        task = task_result.data[0]
        
        # Parse the quiz questions
        quiz_content = task.get('quiz_data')
        if not quiz_content:
            error_msg = 'No quiz data found.'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))
            
        questions = parse_quiz_questions(quiz_content)
        if not questions:
            error_msg = 'Could not parse quiz questions.'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))
        
        # Calculate score
        score = 0
        total_questions = len(questions)
        user_answers = {}
        question_results = []
        
        for i, question in enumerate(questions, 1):
            field_name = f'question_{i}'
            user_answer = request.form.get(field_name, '').strip()
            correct_answer = question.get('correct_answer', '').upper()
            is_correct = user_answer.upper() == correct_answer
            
            user_answers[field_name] = user_answer
            
            if is_correct:
                score += 1
            
            # Prepare question result for response
            question_results.append({
                'question': question['question'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'correct': is_correct
            })
        
        # Calculate percentage
        percentage = (score / total_questions) * 100 if total_questions > 0 else 0
        passing_score = int(task.get('passing_score', 70))
        passed = percentage >= passing_score
        
        # Verify user exists in profiles table
        try:
            profile_data = supabase.table('profiles').select('*').eq('id', user_id).execute()
            if not profile_data.data:
                # If user doesn't exist in profiles, create a basic profile
                supabase.table('profiles').insert({
                    'id': user_id,
                    'email': user_email,
                    'name': full_name or f'User {user_id[:8]}',
                    'role': 'student',
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }).execute()
        except Exception as e:
            print(f"Error checking/creating user profile: {str(e)}")
            # Continue with quiz attempt anyway
        
        # Prepare quiz attempt data
        quiz_attempt = {
            'student_id': user_id,
            'course_id': course_id,
            'module_id': module_id,
            'task_id': task_id,
            'score': float(percentage),
            'passed': passed,
            'answers': user_answers,
            'total_questions': total_questions,
            'correct_answers': score,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Insert quiz attempt
        result = supabase.table('quiz_attempts').insert(quiz_attempt).execute()
        
        # Update progress
        progress_data = {
            'student_id': user_id,
            'course_id': course_id,
            'module_id': module_id,
            'task_id': task_id,
            'status': 'completed' if passed else 'in_progress',
            'completed_at': 'now()' if passed else None,
            'completion_percentage': 100 if passed else 50,
            'updated_at': 'now()'
        }
        
        supabase.table('progress') \
            .upsert(progress_data) \
            .eq('student_id', user_id) \
            .eq('task_id', task_id) \
            .execute()
        
        # Prepare success response
        response_data = {
            'success': True,
            'score': round(percentage, 2),
            'passed': passed,
            'total_questions': total_questions,
            'correct_answers': score,
            'passing_score': passing_score,
            'questions': question_results,
            'message': f'You scored {score} out of {total_questions} ({percentage:.0f}%). '+\
                     (f'Congratulations, you passed! You needed {passing_score}% to pass.' if passed 
                      else f'You needed {passing_score}% to pass.')
        }
        
        if is_ajax:
            return jsonify(response_data)
        
        flash(response_data['message'], 'success' if passed else 'warning')
        return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))
            
    except Exception as e:
        error_msg = f'Error processing quiz: {str(e)}'
        print(error_msg)
        if is_ajax:
            return jsonify({
                'success': False,
                'error': error_msg,
                'details': str(e)
            }), 500
        flash(error_msg, 'error')
        return redirect(url_for('course_task', course_id=course_id, module_id=module_id, task_id=task_id))
