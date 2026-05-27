# CampusActivity Backend Handoff

This branch implements the changed backend contract for the campus activity platform.

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

The updated interface document uses root paths such as `/auth/login`. The app also keeps the old `/api/...` prefix for compatibility, so `/api/auth/login` still works.

## Demo Accounts

Created by `python init_db.py`:

- Student: role `user`, account `2024000001`, password `password123`
- Organizer: role `organizer`, account `org@example.com`, password `password123`
- Admin: role `admin`, account `000001`, password `Admin123456`

## Implemented Modules

- Authentication and profile
- User and organizer registration
- Activity list/detail and organizer activity management
- Registration, cancellation, organizer registration list, rejection, and stats
- Check-in code, user code check-in, manual check-in, user check-in records, and organizer check-in stats
- Notifications and announcements
- Admin review/user management/statistics
- Leaderboard

## Updated Endpoints

Auth and user:

- `POST /auth/register/user`: returns `userId`, `user_id`, `role`, `status`, and `token`
- `POST /auth/register/organizer`: returns `user_id`, `organizer_id`, `role`, `status`, and `token`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /user/profile`
- `PUT /user/profile`
- `POST /user/avatar`: multipart form upload, field `avatar`, jpg/png only, max 2MB, returns `avatar_url`
- `POST /user/reset-password`
- `DELETE /user/account`

Activities and metadata:

- `GET /activities`
- `GET /activities/{activity_id}`
- `POST /organizer/activities`
- `POST /organizer/activities/{activity_id}/submit`
- `PUT /organizer/activities/{activity_id}`
- `DELETE /organizer/activities/{activity_id}`
- `GET /organizer/activities`
- `GET /categories`

Registration:

- `POST /activities/{activity_id}/register`
- `DELETE /activities/{activity_id}/register`
- `GET /user/registrations`
- `GET /organizer/activities/{activity_id}/registrations`
- `POST /organizer/registrations/{registration_id}/reject`
- `GET /activities/{activity_id}/registration-stats`

Check-in:

- `GET /organizer/activities/{activity_id}/checkin-code`
- `POST /activities/{activity_id}/checkin`
- `POST /organizer/activities/{activity_id}/manual-checkin`
- `GET /user/checkins`
- `GET /organizer/activities/{activity_id}/checkins`

Notifications and announcements:

- `GET /notifications`
- `PUT /notifications/{notification_id}/read`
- `POST /admin/announcements`
- `GET /announcements`
- `DELETE /admin/announcements/{announcement_id}`

Admin and stats:

- `GET /admin/activities`
- `PUT /admin/activities/{activity_id}/review`
- `PUT /admin/activities/{activity_id}/remove`
- `GET /admin/users`
- `GET /admin/users/{user_id}`
- `GET /admin/organizers`
- `GET /admin/organizers/{organizer_id}`
- `PUT /admin/organizers/{organizer_id}/review`
- `POST /admin/admins`
- `GET /admin/admins`
- `DELETE /admin/admins/{admin_id}`
- `GET /admin/statistics`
- `GET /leaderboard`

## Removed Or Changed By The New Contract

- `PUT /notifications/read-all` was removed and now returns 404.
- Check-in code response no longer returns `expires_at`.
- Manual check-in response returns `user_id` and `checkin_time`, not `username`.
- Announcement creation uses `start_time` and `end_time`; `expires_at` is not used.
- Announcement list returns `start_time` and `end_time`.
- Organizer profile no longer returns `reject_reason`.
- Public activity list items no longer include `status`.
- Registration stats include `total_checked`.
- Organizer check-in stats include `notCheckedIn`.

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

## Verification

Commands run locally:

```bash
python -X utf8 -m py_compile app/__init__.py app/api/v1/auth.py app/api/v1/user.py app/api/v1/activities.py app/api/v1/registrations.py app/api/v1/checkin.py app/api/v1/notifications.py app/api/v1/admin.py app/api/v1/stats.py models.py init_db.py run.py
python -X utf8 init_db.py
```

Smoke-tested with Flask `test_client`:

- user registration auto-login
- organizer/admin login
- profile
- activity list/detail
- user registration
- my registrations
- organizer registration list
- registration stats
- check-in code
- user check-in
- my check-ins
- organizer check-in stats
- admin announcement create/list/delete
- leaderboard
- removed `PUT /notifications/read-all` returns 404

## Notes

- The current project already tracks `instance/campus_activity.db`, but `.gitignore` ignores `instance/` and `*.db`. Local smoke tests may modify the database file; do not commit it unless the team intentionally wants to version a demo database.
- The existing structure already separates API blueprints under `app/api/v1` and shared services under `app/services`. A future refactor can rename `api/v1` to `controllers` and move more business logic into service files, but this branch prioritizes matching the changed API contract without disrupting working code.
