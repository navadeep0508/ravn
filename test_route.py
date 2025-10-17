from app import app

with app.test_client() as client:
    try:
        response = client.get('/course/c51c9b68-682a-4b72-bedc-ca0ce5a426ee/module/bcc4ca73-a56a-443c-8f63-ffa21e030d03/tasks')
        print('Status:', response.status_code)
        print('Response:', response.get_data(as_text=True)[:500])
    except Exception as e:
        print('Error:', e)
