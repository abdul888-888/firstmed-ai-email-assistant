# Requirements Specification: Departmental RBAC & Multi-Department Collaboration Workflow

## 1. Executive Summary
Transform the FirstMed AI Assistant from a unified inbox into a **Department-Isolated, Role-Gated Collaboration Workspace**. Staff members are restricted to viewing and managing emails specific to their assigned clinical or operational department (`FRONT_OFFICE`, `PHYSIOTHERAPY`, `GASTROENTEROLOGY`, `LABORATORY`, `NURSE_SPECIALIST`), while system administrators (`ADMIN`) maintain global visibility and user lifecycle control.

---

## 2. User Roles & Access Control Matrix

### Supported Roles
1. `ADMIN`: Full system access, user management, shift management, global inbox view, template management.
2. `FRONT_OFFICE`: Handles general inquiries, appointment requests, initial triage, and routing.
3. `PHYSIOTHERAPY`: Manages musculoskeletal consultations, rehabilitation scheduling, and therapy inquiries.
4. `GASTROENTEROLOGY`: Handles GI procedures, endoscopy queries, and specialist appointments.
5. `LABORATORY`: Manages lab test results, bloodwork inquiries, and diagnostic sample status.
6. `NURSE_SPECIALIST`: Manages clinical triage, prescription refills, procedure follow-ups, and urgent medical advice.

### Access Control Rules
* Staff users (`FRONT_OFFICE`, `PHYSIOTHERAPY`, `GASTROENTEROLOGY`, `LABORATORY`, `NURSE_SPECIALIST`) can ONLY view email threads where `target_department` matches their active department role, OR emails explicitly re-assigned to their department.
* `ADMIN` users can view all emails across all departments and filter by any department.
* Email actions (drafting, sending, reassigning) are role-gated.

---

## 3. Backend Functional Requirements

### A. JWT Auth & Dependency Guards
* Embedded Claims: Include `roles` (array or primary role string), `department`, and `is_on_shift` inside JWT payload.
* FastAPI Dependency Guards: Implement helper dependencies like `require_roles(["ADMIN", "PHYSIOTHERAPY"])`.

### B. Email Classification & Department Isolation
* Triage Engine: Update LLM classification output schema to include `target_department` (enum of supported departments) along with `confidence_score` and `category`.
* Strict Manual Safety Overrides: Hardcode safety rules in triage service:
  * Categories: `Lab Results`, `Medical Advice`, `Procedure Bookings`, `Emergency`
  * Action: Flag `manual_handling_required = true`, bypass AI draft generation, route immediately to `LABORATORY` or `NURSE_SPECIALIST`.

### C. Admin User & Shift Management API (`/admin/users`)
* `GET /api/v1/admin/users`: List users with role, department, and shift status (`is_on_shift`, `shift_started_at`).
* `POST /api/v1/admin/users`: Create user with role and initial department.
* `PUT /api/v1/admin/users/{user_id}`: Update user role, department, active status, or shift state.

### D. Cross-Department Collaboration & Internal Notes
* Model `InternalNote`: `id`, `email_id`, `author_id`, `content`, `mentioned_department`, `created_at`.
* Reassignment API: `POST /api/v1/emails/{id}/reassign` updating `target_department` and logging internal transfer note.
* Notes API: `GET /api/v1/emails/{id}/notes` and `POST /api/v1/emails/{id}/notes` supporting `@department` tags.

---

## 4. Frontend UI Requirements

### A. Department-Filtered Inbox Workspace (`/inbox/[department]`)
* Department switcher / tab bar respecting user's assigned role.
* Real-time email count badges per department for admins.

### B. Admin User Management Screen (`/admin/users`)
* User table displaying Name, Email, Role badge, Department, Shift status toggle, and action buttons.
* User creation / edit modal with role and department dropdowns.

### C. Internal Notes & Re-Assignment Modal
* Slide-over or modal in thread view to enter internal comments.
* Dropdown to transfer ownership to another department with automated `@mention` tagging.

### D. Notion Citation & Verification Panel
* Transparency panel in draft view showing:
  * Matched template identifier (e.g., `GP_Price_ValueCard_v2`).
  * Notion RAG citation cards with exact source snippets and page links.
  * AI workflow rule applied during classification.
