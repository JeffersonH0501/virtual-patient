# Organization user administration

Only authenticated superusers can list, create or update managed accounts. Targets must
belong to the superuser's organization and have the student or teacher role. The configured
superuser is provisioned separately and cannot be edited using these endpoints.

| Operation | Endpoint | Response |
| --- | --- | --- |
| List | GET /users/admin?offset=0&limit=100 | User array and X-Total-Count header |
| Create | POST /users/admin | 201 User |
| Partial update | PATCH /users/admin/{user_id} | 200 User |

PATCH accepts only name, email, role and password. Each field is optional, but explicitly
supplied null values are rejected. Names are trimmed and cannot be blank. Emails are trimmed,
normalized to lowercase, validated and checked for uniqueness. Roles are student or teacher.
Supplied passwords cannot be empty or whitespace-only; their actual content is preserved and
hashed with the existing password hasher. Omitted passwords retain the existing hash.

The response uses the existing User schema and never includes passwords, hashes or session
tokens. Account IDs, organization membership, interviews and language preferences remain
unchanged. Migration 032 adds the nullable created_at registration timestamp.

| Failure | Status |
| --- | --- |
| Missing or invalid authentication | 401 |
| Authenticated actor without superuser access | 403 |
| Missing target, other organization, or superuser target | 404 |
| Duplicate normalized email, including a uniqueness race | 409 |
| Invalid fields, extra fields, prohibited role or explicit null | 422 |

The UI keeps the administrator session, separates list errors from save errors, retains
failed form input, prevents duplicate saves, and clears password state when the editor closes.
Public registration and /users/me retain their restrictions. Password changes preserve the
existing session/token lifetime behavior; this endpoint does not add token revocation.
Authorization checks read the current role from the database.

## Verification

Run from the existing virtual-patient Docker Compose project:

```bash
docker compose -f docker-compose.local.yml exec api python -m pytest app/routers/tests/test_managed_users.py -q
docker compose -f docker-compose.local.yml exec ui yarn vitest run src/components/Users/Users.test.tsx src/services/users/manageUsers.test.ts --environment jsdom
```

API tests use isolated synthetic accounts and do not edit the running project database.

The list response body remains an array. X-Total-Count contains the total number of
student/teacher accounts in the authenticated superuser organization, before applying
offset/limit. CORS exposes this header to the UI. The client uses it for exact user ranges
and numbered pages, and refreshes it after account creation or editing. Deploy API and UI
together; the client requires the total header and never guesses it from page size.

Registration date is server-generated with a timezone-aware database timestamp for newly
created accounts and exposed as created_at (createdAt in the UI). Migration 032 first adds
the nullable column without a default, then enables the default for future inserts. Legacy
accounts keep NULL; no migration timestamp or interview date is presented as registration.
The UI displays Not available when the date is unknown. Registration date is read-only.

The UI requests five accounts per page using the shared LIST_PAGE_SIZE. Editing uses the Password label, leaves the field empty, and enables Save changes only for valid meaningful changes. PATCH includes only modified fields; opening the editor and toggling password visibility do not mark it changed.
