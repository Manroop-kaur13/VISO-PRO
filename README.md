# VISO PRO

VISO PRO keeps its existing static workstation UI in code/outputs/ and serves
the backend from backend/. The UI calls the FastAPI service over HTTPS in
production; secrets stay on the backend.

## What is connected

- Clinician registration, login, logout, and current-user authentication.
- Protected patient list/create, profile, imaging sessions, annotation, and
  capture endpoints.
- PostgreSQL persistence through SQLAlchemy and Alembic.
- Private S3-compatible object storage for uploaded images/video, with metadata
  in PostgreSQL and short-lived signed retrieval links.
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

Image storage is optional for the current deployment. Without S3-compatible
storage configured, sign-in and database-backed patient/profile features work,
but image uploads are unavailable and /ready reports object_storage as
not_configured. Add S3-compatible storage later when ready.

When you are ready to enable image uploads, create a private Amazon S3 bucket
(or another S3-compatible bucket) and give the backend access to only that
bucket. In AWS, keep Block Public Access enabled and ACLs disabled. Do not use
root-account access keys.

For an AWS IAM policy attached to the backend's IAM user, replace
YOUR_BUCKET_NAME with the bucket name and use:

~~~
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    }
  ]
}
~~~

Create a dedicated IAM user for the backend, attach that policy, and create an
access key for an application running outside AWS. Put the access key only in
backend/.env locally and in Render's environment settings for deployment.
Configure VISO_S3_BUCKET, VISO_S3_REGION, VISO_S3_ACCESS_KEY_ID, and
VISO_S3_SECRET_ACCESS_KEY. Leave VISO_S3_ENDPOINT_URL blank for AWS S3; set it
to the provider's S3 API endpoint for another S3-compatible service. Never put
storage credentials in code/outputs/config.js or send them in chat.

Restart the API after setting storage values. GET /ready should report
object_storage as ready only after the backend can reach the bucket.

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
   the service root to backend.
3. During setup, provide:
   - VISO_DATABASE_URL: PostgreSQL URL for the app role, not the database
     owner URL.
   - Render generates VISO_AUTH_TOKEN_SECRET automatically.
   - S3 settings are intentionally omitted for now; image uploads remain
     unavailable until storage is configured.
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

- A private object-storage bucket and backend access credentials/role must be
  configured.
- Render and Vercel need to be deployed and connected to the correct API URL.
