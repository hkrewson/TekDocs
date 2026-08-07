# ADR 0001: Greenfield application stack

- Status: Accepted
- Date: 2026-08-07

## Decision

Use Django 5.2 LTS and Django REST Framework with PostgreSQL, Celery, and Valkey. Use a separately built React 19/TypeScript/Vite frontend served through a same-origin proxy. Package the reference deployment with Docker Compose.

Authentication will use Django and django-allauth rather than copied application-specific authentication code. Migrations are the only schema source of truth.

## Consequences

The application gains mature authentication, migration, policy, mail, task, and administrative foundations while retaining a purpose-built frontend. The split build adds API-contract and container coordination, which OpenAPI generation and Compose tests must cover.
