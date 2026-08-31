# Helpdesk — Support Ticket System

A role-based support desk built with Django REST Framework and MySQL. Customers raise
tickets, agents work them, SLA deadlines are enforced automatically, and every status
change is permanently recorded.

![CI](https://github.com/YOUR_USERNAME/helpdesk/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Django](https://img.shields.io/badge/django-6.0-092E20)
![Tests](https://img.shields.io/badge/tests-102%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)

**Live demo:** _add your URL after deploying_

---

## What it does

| Role | Can do |
|---|---|
| **Customer** | Raise tickets, see only their own, reply to them |
| **Agent** | See every ticket, change status and priority, write internal notes |
| **Admin** | Everything, plus delete tickets and manage users |

The workflow it models:

1. A customer raises a ticket
2. The system sets an SLA deadline from the priority — 4h urgent, 24h high, 72h medium, 168h low
3. An agent picks it up; the status moves to In Progress
4. Customer and agent talk on the ticket
5. Agents leave internal notes the customer never sees
6. Every status transition is written to an audit trail
7. Notification emails are sent by a background worker, never inside the request

---

## Screenshots

_Add screenshots of the ticket list, ticket detail, and the Django admin here._

---

## Tech stack

**Backend** — Django 6.0, Django REST Framework 3.18, SimpleJWT, django-filter, MySQL 8
**Background jobs** — django-q2 with the ORM broker (no Redis required)
**Frontend** — HTML, CSS, and vanilla JavaScript. No framework, no build step
**Testing** — pytest, pytest-django, factory-boy, coverage
**Deployment** — Gunicorn, WhiteNoise, GitHub Actions

---

## Architecture

```
┌──────────────────┐        JSON over HTTP        ┌──────────────────┐
│    frontend      │ ───────────────────────────► │   Django + DRF   │
│  HTML/CSS/JS     │ ◄─────────────────────────── │      :8000       │
│     :5500        │        JWT in headers        └────────┬─────────┘
└──────────────────┘                                       │
                                                           ▼
                          ┌──────────────────┐      ┌──────────────┐
                          │  qcluster worker │ ◄──► │    MySQL     │
                          │  emails, SLA     │      │  data + queue│
                          └──────────────────┘      └──────────────┘
```

The frontend and API are entirely separate programs communicating over HTTP, so the
frontend could be replaced with React without changing a line of backend code.

The task queue lives in MySQL rather than Redis, which means the whole system runs on
one database and no extra service.

### Apps

| App | Responsibility |
|---|---|
| `accounts` | Custom user model (email login, three roles), registration, JWT auth |
| `tickets` | Ticket, Comment, StatusChange models; the API; permissions |
| `notifications` | Background email tasks and the scheduled SLA sweep |

---

## Notable implementation details

**Custom user model from day one.** Email is the login field; `username` is removed
entirely. Defined before the first migration, because changing it afterwards means
repointing every foreign key in a populated database.

**Three layers of authorization.** Authentication (JWT) answers *who are you*.
Queryset filtering in `get_queryset()` decides *which rows exist for you* — this is
what protects list endpoints, since DRF's object permissions never run for lists.
Permission classes then gate *what you may do* to a single object.

**404, not 403, for another customer's ticket.** Returning 403 would confirm the ticket
exists, letting someone enumerate the database by walking ids. Filtering the queryset
makes it indistinguishable from a ticket that was never created.

**N+1 queries eliminated.** Serializing 20 tickets costs 41 queries without
`select_related` and 1 with it. A test asserts the query count does not grow with the
number of rows, so the optimization cannot silently regress.

**Business logic lives in the model.** The SLA deadline is computed in `Ticket.save()`,
so it applies identically through the API, the admin, the shell, and tests — rather than
being reimplemented per entry point.

**Emails are queued, never sent inline.** Sending mail inside a view blocks the response
on network I/O, and a mail-server outage would stop customers raising tickets. Tasks are
enqueued inside `transaction.on_commit` so the worker cannot read a row before it is
committed.

**Internal notes are hidden in two places.** A `SerializerMethodField` filters them out
of API responses for customers, and the notification task refuses to email them. Missing
either one would leak the content.

---

## Running it locally

### Prerequisites

- Python 3.13+
- MySQL 8.0+ running locally

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/YOUR_USERNAME/helpdesk.git
cd helpdesk
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
```

### 2. Install dependencies

```bash
pip install -r backend/requirements-dev.txt
```

### 3. Create the database

```sql
CREATE DATABASE ticket CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Configure the environment

```bash
cd backend
copy .env.example .env          # Windows
cp .env.example .env            # macOS / Linux
```

Edit `.env` and set at minimum `DJANGO_SECRET_KEY` and `DB_PASSWORD`. Generate a key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Migrate and create an admin user

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_schedules
```

### 6. Run all three processes

Each needs its own terminal:

```bash
# 1 — the API
cd backend && python manage.py runserver

# 2 — the frontend
cd frontend && python -m http.server 5500

# 3 — the background worker
cd backend && python manage.py qcluster
```

Open **http://127.0.0.1:5500/index.html**.

> The frontend must be served over HTTP. Opening `index.html` directly as a `file://`
> URL will not work, because ES modules are blocked on that protocol.

---

## Running the tests

```bash
cd backend
pytest                                      # 102 tests
pytest --cov=accounts --cov=tickets --cov=notifications --cov-report=term-missing
pytest -k "permission"                      # just the security tests
```

Tests run against a separate `test_ticket` database that is created and destroyed
automatically. Your development data is never touched.

---

## API reference

All endpoints require `Authorization: Bearer <access-token>` except register and login.

### Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/auth/register/` | Create an account (always a customer) |
| `POST` | `/api/auth/login/` | Exchange email + password for tokens |
| `POST` | `/api/auth/token/refresh/` | Get a new access token |
| `POST` | `/api/auth/token/verify/` | Check whether a token is still valid |
| `GET` `PATCH` | `/api/auth/me/` | Read or update your own profile |

### Tickets

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/tickets/` | List (scoped to your role) |
| `POST` | `/api/tickets/` | Raise a ticket |
| `GET` | `/api/tickets/{id}/` | One ticket with comments and history |
| `PATCH` | `/api/tickets/{id}/` | Update (staff-only fields enforced) |
| `DELETE` | `/api/tickets/{id}/` | Delete (admin only) |

### Comments

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/comments/` | List (internal notes hidden from customers) |
| `POST` | `/api/comments/` | Reply to a ticket |
| `PATCH` `DELETE` | `/api/comments/{id}/` | Edit or remove your own |

### Filtering, search, and ordering

```
GET /api/tickets/?status=OPEN&priority=URGENT
GET /api/tickets/?search=password           # title, description, or requester email
GET /api/tickets/?ordering=sla_due_at       # prefix with - to reverse
GET /api/tickets/?page=2
```

### Example

```bash
# Log in
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}'

# Use the access token
curl http://127.0.0.1:8000/api/tickets/ \
  -H "Authorization: Bearer <access-token>"
```

Responses are paginated at 20 per page:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 32,
      "title": "Wifi drops every ten minutes",
      "status": "IN_PROGRESS",
      "status_display": "In Progress",
      "priority": "MEDIUM",
      "created_by": { "id": 2, "email": "riya@example.com", "role": "CUSTOMER" },
      "assigned_to": null,
      "sla_due_at": "2026-08-30T13:12:44Z",
      "is_overdue": false
    }
  ]
}
```

---

## Deployment

The project ships a `Procfile` with three process types:

```
web:     gunicorn config.wsgi:application
worker:  python manage.py qcluster
release: python manage.py migrate && python manage.py collectstatic
```

### Required environment variables

| Variable | Example | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | *(50+ random chars)* | Never reuse the development key |
| `DEBUG` | `False` | Must be `False` in production |
| `ALLOWED_HOSTS` | `helpdesk.example.com` | Comma-separated |
| `DATABASE_URL` | `mysql://user:pass@host:3306/db` | Or the individual `DB_*` variables |
| `CORS_ALLOWED_ORIGINS` | `https://helpdesk-ui.example.com` | Where the frontend is served |
| `CSRF_TRUSTED_ORIGINS` | `https://helpdesk.example.com` | Needed for the admin over HTTPS |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | | Use an app password, not your real one |
| `DEFAULT_FROM_EMAIL` | `helpdesk@example.com` | |
| `FRONTEND_URL` | `https://helpdesk-ui.example.com` | Used to build links inside emails |

### After the first deploy

```bash
python manage.py createsuperuser
python manage.py setup_schedules      # registers the hourly SLA sweep
```

### Verify the configuration

```bash
python manage.py check --deploy
```

With `DEBUG=False` this should report no security warnings. HSTS, secure cookies, SSL
redirect, and content-type nosniff are all enabled automatically when `DEBUG` is off.

---

## Project layout

```
helpdesk/
├── .github/workflows/ci.yml     tests on every push, against a real MySQL
├── Procfile                     web / worker / release process definitions
├── backend/
│   ├── config/                  settings, root URLs, WSGI
│   ├── accounts/                custom user, JWT auth, registration
│   ├── tickets/                 models, API, permissions
│   ├── notifications/           background email tasks
│   ├── tests/                   102 tests
│   ├── requirements.txt         runtime dependencies
│   └── requirements-dev.txt     plus test tooling
└── frontend/
    ├── index.html               sign in
    ├── register.html            create account
    ├── tickets.html             list and create
    ├── ticket.html              detail, comments, history
    ├── css/styles.css
    └── js/
        ├── api.js               the only file that calls fetch()
        └── ui.js                escaping, dates, form helpers
```

---

## Known limitations

Being explicit about what this does **not** do:

- **No token revocation.** A stolen access token stays valid for its full 30 minutes.
  The production fix is SimpleJWT's blacklist app, which reintroduces a database lookup.
- **Tokens are stored in `localStorage`,** which is readable by any JavaScript on the
  page. `HttpOnly` cookies are safer but require CSRF handling.
- **The task queue polls the database** every two seconds rather than being pushed to.
  Fine at this scale; Celery with Redis is the answer at higher throughput.
- **The frontend shows only the first page** of results — the API paginates, the UI does
  not yet have pagination controls.
- **Emails are plain text** with no HTML alternative and no notification preferences.

---

## License

MIT
