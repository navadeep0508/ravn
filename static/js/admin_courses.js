document.addEventListener('DOMContentLoaded', function() {
    // Handle unenroll button clicks
    document.querySelectorAll('.unenroll-btn').forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault();
            const courseId = this.getAttribute('data-course-id');
            const isEnrolled = this.classList.contains('bg-green-600');
            
            try {
                if (isEnrolled) {
                    // Make API call to unenroll
                    const response = await fetch(`/course/${courseId}/unenroll`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                    });

                    if (response.ok) {
                        // Update button state on success
                        this.innerHTML = '<i class="fas fa-user-plus mr-1"></i>Enroll';
                        this.classList.remove('bg-green-600', 'hover:bg-green-700');
                        this.classList.add('bg-gray-500', 'hover:bg-gray-600');
                    } else {
                        console.error('Failed to unenroll from course');
                        alert('Failed to unenroll from course. Please try again.');
                    }
                } else {
                    // Make API call to enroll
                    const response = await fetch(`/course/${courseId}/enroll`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                    });

                    if (response.ok) {
                        // Update button state on success
                        this.innerHTML = '<i class="fas fa-user-check mr-1"></i>Enrolled';
                        this.classList.remove('bg-gray-500', 'hover:bg-gray-600');
                        this.classList.add('bg-green-600', 'hover:bg-green-700');
                    } else {
                        console.error('Failed to enroll in course');
                        alert('Failed to enroll in course. Please try again.');
                    }
                }
            } catch (error) {
                console.error('Error:', error);
                alert('An error occurred. Please try again.');
            }
        });
    });
});
