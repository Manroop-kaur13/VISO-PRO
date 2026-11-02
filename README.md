# VISO PRO

VISO PRO keeps its existing static workstation UI in code/outputs/ and serves
the backend from backend/. The UI calls the FastAPI service over HTTPS in
production; secrets stay on the backend.

## What is connected

- Clinician registration, login, logout, and current-user authentication.
- Protected patient list/create, profile, imaging sessions, annotation, and
  capture endpoints.
- PostgreSQL persistence through SQLAlchemy and Alembic.
- Private Cloudinary storage for new image/video uploads, with metadata in
  PostgreSQL and five-minute signed retrieval links. Existing S3 records remain
  readable through the retained S3 adapter.
- /health, /ready, and interactive API documentation at /docs.
- Browser authentication uses a short-lived bearer token kept in
  sessionStorage. Patient and capture APIs require a valid token.

The database already had patients, patient_profiles, and captures tables owned
by the database owner role. The VISO migrations preserve those tables and their
data. Migration 0003 adds VISO access/session/storage/annotation tables and
references the existing patients table.

## Local setup (Windows PowerShell)

### 1. Create the Python environment

Open PowerShell in the repository root:

~~~
cd "$HOME\Desktop\Projects\VISO\backend"
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

If virtual-environment activation is blocked, call its Python directly:

~~~
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

### 2. Configure local environment values

~~~
Copy-Item .env.example .env
~~~

Edit backend\.env in VS Code. Set VISO_DATABASE_URL to the PostgreSQL URL
provided by the database owner. Keep the URL private; never paste it into chat
or commit .env.

Generate the auth signing secret locally:

~~~
python -c "import secrets; print(secrets.token_urlsafe(48))"
~~~

Put that output into VISO_AUTH_TOKEN_SECRET. It must be at least 32 characters.
Do not use the sample placeholder in a running service.

Image storage is optional. Without Cloudinary credentials, authentication and
database-backed patient/profile features work, but image uploads are disabled
and `/ready` reports object storage as `not_configured`.

To enable Cloudinary locally, set `CLOUDINARY_CLOUD_NAME`,
`CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` in `backend/.env`, and set
`VISO_STORAGE_PROVIDER=cloudinary`. New media is uploaded with Cloudinary's
`authenticated` delivery type. The API returns time-limited signed retrieval
URLs after checking the clinician's access to the patient. Keep credentials
only in the backend environment; never put them in frontend files or Git.

The S3 adapter and `VISO_S3_*` settings remain available for rollback and for
previous S3-backed records. To direct new uploads to S3 again, set
`VISO_STORAGE_PROVIDER=s3` and provide the S3 settings. Stored records are
provider-tagged, so previously uploaded Cloudinary assets remain routable when
the provider setting changes.

`/ready` distinguishes missing storage configuration from an unavailable
provider: credentials alone do not mark storage ready. The backend must also
successfully ping Cloudinary (or reach the configured S3 bucket).

#### AWS Academy Learner Lab note

Learner Lab credentials are temporary. The backend accepts the lab's session
token through VISO_S3_SESSION_TOKEN so you can test S3 locally while the lab
session is active. When AWS gives you new credentials, update all three values
(VISO_S3_ACCESS_KEY_ID, VISO_S3_SECRET_ACCESS_KEY, and
VISO_S3_SESSION_TOKEN) and restart the API. These credentials expire and are
not suitable for a continuously running Render service. For deployment, use a
storage account that provides persistent S3-compatible application credentials
(or an AWS account/role intended for hosting), and configure its endpoint if
required. Never paste temporary credentials into chat or commit them.

### 3. Run migrations

Migrations 0001 through 0003 have now been applied to the shared Neon database.
The app role owns the VISO patient-access, imaging-session, stored-capture, and
annotation tables. The grant on the existing patients table only allows foreign
keys; it did not change patient rows. To check the migration state from backend:

~~~
python -m alembic current
~~~

### 4. Start the API and frontend

Terminal 1, from backend:

~~~
python -m uvicorn app.main:app --reload
~~~

Terminal 2, from code\outputs:

~~~
py -3 -m http.server 5500
~~~

Open http://localhost:5500. The local frontend uses
http://127.0.0.1:8000; browser camera access works on localhost. Avoid opening
the HTML with file://, which browsers restrict for cross-origin API calls.

Open http://127.0.0.1:8000/docs for Swagger. Confirm /health returns
{"status":"ok"}. /ready should report both database and object storage as
ready after those services are configured and reachable; until then it
correctly returns HTTP 503.

## Frontend deployment

code/outputs/config.js contains only the public API base URL. It currently
uses https://viso-pro-api.onrender.com, matching the Render service name in
render.yaml. If Render assigns a different URL, replace that public URL,
commit the change, and redeploy the existing Vercel frontend. Do not place
database, signing, or storage secrets in this file or in Vercel frontend
variables.

The deployed Vercel origin is included in the backend CORS default:
https://viso-pro.vercel.app. If you use a Vercel preview or another custom
domain, add that exact origin to VISO_CORS_ORIGINS in the backend environment.

## Render deployment

1. Push the repository to the Git provider connected to Render.
2. In Render, create a Blueprint from the repository root. render.yaml sets
   the service root to backend and the web service plan to Free.
3. During setup, provide:
   - VISO_DATABASE_URL: PostgreSQL URL for the app role, not the database
     owner URL.
   - Render generates VISO_AUTH_TOKEN_SECRET automatically.
   - Set `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
     `CLOUDINARY_API_SECRET` in the Render service environment.
   - `VISO_STORAGE_PROVIDER=cloudinary` is set by `render.yaml`.
4. Deploy and verify https://<your-render-service>/health. /ready will return
   HTTP 503 with object_storage not_configured until storage is configured.
5. Update code/outputs/config.js if the actual service URL differs, then
   redeploy Vercel.
6. Sign in through the VISO PRO header, create a synthetic patient record, and
   test notes, annotations, capture upload, library preview, and deletion only
   with synthetic records.

The Render health check uses /health so deployment can start before database or
storage configuration is complete. /ready checks all required services.

## API summary

- POST /auth/register, POST /auth/login, POST /auth/logout, GET /auth/me
- GET /api/patients, POST /api/patients
- GET and PUT /api/patients/{patient_id}/profile
- GET /api/patients/{patient_id}/sessions
- GET and POST /api/patients/{patient_id}/captures
- GET /api/patients/{patient_id}/captures/{image_id}/download
- DELETE /api/patients/{patient_id}/captures/{image_id}
- GET /health, GET /ready, GET /docs

Uploaded media is limited to 15 MiB for images and 25 MiB for videos. Supported
types are JPEG, PNG, WebP, WebM, and MP4. The API checks both declared MIME
type and file signature. Reference-preview images are never sent as patient
captures.

## Tests

With the backend virtual environment active:

~~~
cd "$HOME\Desktop\Projects\VISO\backend"
python -m pytest -v
~~~

Tests use in-memory SQLite and synthetic records; they do not connect to the
shared patient database or use real patient data.

## Environment variables

See backend/.env.example for the complete local variable list. .env is ignored
by Git. Never put a secret in frontend code, committed test fixtures, or project
documentation.

## External setup still required

- Cloudinary credentials must be configured on the Render backend to enable
  uploads. No frontend credentials are used.
- Render and Vercel need to be deployed and connected to the correct API URL.
