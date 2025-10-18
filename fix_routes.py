import os
import re

template_dir = r'c:\Users\NAVADEEP\Documents\ravn\templates'

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace all occurrences
            new_content = content.replace('admin_course_modules', 'teachers_course_modules')
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'Updated: {filepath}')
