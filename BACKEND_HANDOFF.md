# CampusActivity Backend Handoff

This fork implements the backend APIs for:

- Authentication and profile
- User/organizer registration
- Activity registration management
- Check-in code, manual check-in, and check-in records

## Run Locally

```bash
python -m pip install -r requirements.txt
python init_db.py
python run.py
```

Server:

```text
http://127.0.0.1:5000
```

## Demo Accounts

Created by `python init_db.py`:

- Student: role `user`, account `2024000001`, password `password123`
- Organizer: role `organizer`, account `org@example.com`, password `password123`
- Admin: role `admin`, account `000001`, password `Admin123456`

## Implemented Endpoints

Auth:

- `POST /api/auth/register/user`
- `POST /api/auth/register/organizer`
- `POST /api/auth/login`
- `POST /api/auth/logout`

Profile:

- `GET /api/user/profile`
- `PUT /api/user/profile`
- `DELETE /api/user/account`

Registration:

- `POST /api/registrations`
- `DELETE /api/registrations/{activity_id}`
- `GET /api/registrations/my`
- `GET /api/activities/{activity_id}/registrations`
- `PUT /api/activities/{activity_id}/registrations/{user_id}/reject`
- `GET /api/activities/{activity_id}/registration-stats`

Check-in:

- `GET /api/activities/{activity_id}/checkin-code`
- `POST /api/checkin`
- `POST /api/activities/{activity_id}/manual-checkin`
- `GET /api/checkin/my`
- `GET /api/activities/{activity_id}/checkin-stats`

## Frontend Contract

All protected APIs require:

```text
Authorization: Bearer <token>
```

All responses use:

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

## Notes For Pull Request

- `init_db.py` is now repeatable and also patches old SQLite databases with the new `activity.current_participants` and `registration.slot_release_at` columns.
- Passwords are stored with Werkzeug hashes.
- The repository currently tracks `instance/campus_activity.db` and several `__pycache__` files from before this work. They should ideally be removed from Git tracking in a cleanup PR, but this implementation does not delete them automatically.
- The local smoke test used activity ID `1`, which is created by `python init_db.py`.
