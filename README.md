# Smart Vehicle Inspection & Fleet Management System

A complete, responsive, multilingual **Smart Vehicle Inspection & Fleet Management System** built with **Python Flask** and **Flask-SQLAlchemy**, using SQLite for local development and supporting PostgreSQL for shared production deployments.

## Core Capabilities

1. **Authentication & Account Management (`Employee ID` + `Password`)**
   - Sign in exclusively with **Employee ID** and **Password** (no email login, no public self-registration).
   - Only a signed-in **Admin** can register employees, assign roles (`admin`, `supervisor`, `driver`), set initial passwords (minimum 12 characters, stored as Werkzeug `scrypt` hashes), and deactivate or reactivate accounts.
   - Includes CSRF protection on all state-changing forms and JSON endpoints, `Remember me` session persistence, and a password visibility toggle on the login screen.
   - Includes a command-line first-Admin provisioning command (`flask --app app create-admin`).

2. **Role-Based Dashboards & Strict Server-Side Access Control**
   - **Admin**: Fleet KPI summary (Total Vehicles, Total Employees, Inspections Today, Open Faults), Inspection Status SVG donut chart, Monthly Inspections bar chart, Recent Inspections table, employee registration/deactivation, vehicle registration & supervisor assignment, daily driver-to-vehicle scheduling, 31-item checklist management, search, audit log viewer, and multi-sheet Excel export.
   - **Supervisor**: Restricted strictly to vehicles assigned to that supervisor. Displays Assigned Vehicles, Active Drivers, Inspections Today, Pending Faults, Vehicle Status donut chart, Weekly Inspections bar chart, 1-click Supervisor inspection approval/sign-off, fault resolution workflow (`Action taken`), and scoped Excel export.
   - **Driver**: Restricted strictly to the driver's assigned vehicle(s) for the current date. Supports opening the daily inspection via QR code scan (`/scan/<token>`) or Vehicle No. lookup, completing the 31-row inspection checklist, attaching fault photos, saving local drafts, queueing offline submissions in IndexedDB, and viewing personal inspection/fault history.

3. **Daily 31-Point Inspection Checklist (Authoritative Paper Form Order)**
   1. Light & Indicator
   2. Mirrors
   3. Blind spot mirror
   4. Horn
   5. Fuel
   6. Seat Belt
   7. Communication Radio / Tape
   8. A/C in Vehicle
   9. Body Damage
   10. Tyres, nut & bolts
   11. Load Restraint
   12. Battery
   13. Oil Level
   14. Water Level
   15. Steering
   16. Wipers & Wind Screen
   17. Brakes
   18. First Aid Box
   19. Fire Extinguishers
   20. Jack, Tools, Triangle
   21. Vehicle registration papers
   22. Ladder condition
   23. IVMS
   24. Housekeeping
   25. 360 degree Walk around
   26. RAS Sticker OPAL
   27. Driver’s Mandatory Training Cards
   28. Driver Name *(Autofilled from authenticated driver)*
   29. Driver Signature *(Captured typed signature)*
   30. Driver’s ROP EXP Date *(Captured ROP license expiry date)*
   31. Supervisor / PA Signature *(Recorded via Supervisor approval workflow)*

4. **One-Driver-Per-Day & One-Vehicle-Per-Day Assignment Rules**
   - Enforced at both the SQLAlchemy/database constraint level (`UniqueConstraint('vehicle_id', 'day')` and `UniqueConstraint('driver_id', 'day')`) and server validation logic.

5. **Vehicles, QR Codes, Faults & Private Photos**
   - Downloadable PNG QR codes (`/vehicle/<id>/qr.png`) encoding `/scan/<token>`.
   - Marking any checklist item `Not OK` (`fail`) automatically creates an open `Fault` record linked to the inspection and checklist answer.
   - Uploaded fault photos are validated by file extension (`.jpg`, `.jpeg`, `.png`, `.webp`), magic bytes header, and file size (max 5 MB per photo), stored outside `static/` in `private_uploads/`, and served only through the authenticated, role-verified `/fault-photo/<filename>` route.

6. **Four Languages & RTL Accessibility**
   - Full UI, checklist items, status badges, and Excel workbook sheet/column translations for **English (`en`)**, **Arabic (`ar` - RTL)**, **Hindi (`hi` - LTR)**, and **Urdu (`ur` - RTL)**.

7. **PWA & Offline IndexedDB Sync**
   - Web App Manifest (`/manifest.webmanifest`), Service Worker (`/sw.js`), and in-app install button.
   - Drivers who open an assigned inspection while online can save checklist responses offline in IndexedDB (`fleet-offline-v1`) and automatically or manually resynchronize via `POST /api/inspections` when connectivity returns, with duplicate submission prevention and automatic private cache clearing upon sign-out.

---

## Local Setup & First-Admin Instructions

### 1. Create Virtual Environment & Install Dependencies

Requires Python 3.10 or newer:

```bash
python3 -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
export SECRET_KEY="replace-with-a-long-random-secret"
export APP_TIMEZONE="Asia/Muscat"
# Optional: defaults to sqlite:///fleet.db
export DATABASE_URL="sqlite:///fleet.db"
```

### 3. Initialize Database (Seeds the 31 Authoritative Checklist Rows)

```bash
flask --app app init-db
```

### 4. Create the First Administrator Account from the Command Line

Interactive mode:

```bash
flask --app app create-admin
```

Non-interactive CLI flags mode:

```bash
flask --app app create-admin --employee-id EMP-ADMIN --name "System Administrator" --password "AdminPass1234!"
```

*(Optional)* Seed deterministic sample vehicles, supervisors, drivers, and inspections:

```bash
flask --app app seed-demo
```

### 5. Run the Server

Development server:

```bash
flask --app app run --host=0.0.0.0 --port=5000
```

Production WSGI server (Gunicorn):

```bash
gunicorn -b 0.0.0.0:8000 --workers 3 app:app
```

---

## Shared Deployment with PostgreSQL

To switch from local SQLite (`fleet.db`) to a shared **PostgreSQL** database in production:

1. Install the PostgreSQL driver in your environment:
   ```bash
   pip install psycopg2-binary
   ```
2. Provision a PostgreSQL database (e.g., `fleet_db`) and set `DATABASE_URL`:
   ```bash
   export DATABASE_URL="postgresql+psycopg2://fleet_user:strong_password@db.example.com:5432/fleet_db"
   export SECRET_KEY="your-64-char-production-secret"
   export HTTPS="1"
   ```
3. Initialize the schema and 31 checklist rows on PostgreSQL:
   ```bash
   flask --app app init-db
   flask --app app create-admin
   ```
4. Mount `private_uploads/` on persistent storage with restricted filesystem permissions and run behind TLS/HTTPS.
