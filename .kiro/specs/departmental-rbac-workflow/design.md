# Design & Technical Architecture Specification: Departmental RBAC & Workflow Isolation

## 1. System Architecture Overview

```mermaid
graph TD
    Client[React/Vite Frontend] -->|JWT with Role & Department| API[FastAPI Gateway]
    API --> Auth[Role-Guard Middleware]
    Auth --> Triage[Email Triage & Routing Engine]
    Auth --> Admin[User & Shift Admin Service]
    Auth --> Collab[Internal Notes & Reassignment Service]
    Triage -->|Rule Check| Overrides{Safety Override?}
    Overrides -->|Yes (Lab/Emergency/Advice)| Manual[Target: LAB/NURSE + Manual Handling = True]
    Overrides -->|No| LLM[LLM Classification + RAG Notion Citations]
    Admin --> DB[(PostgreSQL Database)]
    Collab --> DB
    Triage --> DB
```

---

## 2. Database Schema Modifications

### A. Updated `users` Table
```sql
ALTER TABLE users ADD COLUMN department VARCHAR(50) DEFAULT 'FRONT_OFFICE';
ALTER TABLE users ADD COLUMN is_on_shift BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN shift_started_at TIMESTAMP WITH TIME ZONE;
```

### B. New `user_role` Enum & Roles
* Values: `'ADMIN'`, `'FRONT_OFFICE'`, `'PHYSIOTHERAPY'`, `'GASTROENTEROLOGY'`, `'LABORATORY'`, `'NURSE_SPECIALIST'`

### C. Updated `email_messages` Table
```sql
ALTER TABLE email_messages ADD COLUMN target_department VARCHAR(50) DEFAULT 'FRONT_OFFICE';
ALTER TABLE email_messages ADD COLUMN manual_handling_required BOOLEAN DEFAULT FALSE;
ALTER TABLE email_messages ADD COLUMN confidence_score FLOAT DEFAULT 1.0;
ALTER TABLE email_messages ADD COLUMN category VARCHAR(100);
```

### D. New `internal_notes` Table
```sql
CREATE TABLE internal_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID NOT NULL REFERENCES email_messages(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    mentioned_department VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Backend API Specifications

### Admin Endpoints (`/api/v1/admin/users`)
* `GET /api/v1/admin/users` -> `List[UserResponse]` (Requires `ADMIN` role)
* `POST /api/v1/admin/users` -> `UserResponse` (Create user with role & department)
* `PUT /api/v1/admin/users/{id}` -> `UserResponse` (Update role, department, `is_on_shift`)

### Email Inbox Endpoints (`/api/v1/emails`)
* `GET /api/v1/emails?department={dept}` -> Scoped email list. Non-admin users are forced to `department = current_user.role`.
* `POST /api/v1/emails/{id}/reassign` -> Payload: `{ "target_department": "PHYSIOTHERAPY", "note": "Transferring orthopaedic referral" }`
* `GET /api/v1/emails/{id}/notes` -> List of internal notes.
* `POST /api/v1/emails/{id}/notes` -> Add internal note with `@mention` parsing.

---

## 4. Frontend Component Architecture

1. `AdminUsersPage.tsx`: Admin interface for user management, shift monitoring, role assignment.
2. `DepartmentInbox.tsx`: Workspace view displaying inbox filtered by active department, role badges, and department tabs for Admins.
3. `InternalNotesDrawer.tsx`: Embedded drawer for internal staff discussion and transfer log.
4. `NotionCitationDrawer.tsx`: Inspector panel rendering:
   * Template name badge (e.g. `GP_Price_ValueCard_v2`).
   * Source citations extracted during RAG.
   * Safety override notice / AI classification confidence score.
