# Setup

radio-gaga uses two `.env` files — one for the backend/scripts, one for the frontend. Neither is committed to the repository.

---

## `/.env` — root (used by `generate_data.py`)

Create a `.env` file at the repo root:

```env
ORTHANC_URL=https://your-orthanc-instance.example.com
ORTHANC_USER=your_username
ORTHANC_PASSWORD=your_password
ORTHANC_OUTPUT_DIR=/data/studies        # optional, defaults to /data/studies
```

| Variable             | Required | Description                                      |
|----------------------|----------|--------------------------------------------------|
| `ORTHANC_URL`        | yes      | Base URL of your Orthanc server                  |
| `ORTHANC_USER`       | yes      | Orthanc HTTP auth username                       |
| `ORTHANC_PASSWORD`   | yes      | Orthanc HTTP auth password                       |
| `ORTHANC_OUTPUT_DIR` | no       | Local directory where studies are downloaded     |

---

## `/backend/.env` — backend (used by FastAPI)

Create a `.env` file inside the `backend/` directory:

```env
OPENROUTER_TOKEN=sk-or-...
```

| Variable            | Required | Description                                      |
|---------------------|----------|--------------------------------------------------|
| `OPENROUTER_TOKEN`  | yes      | API key from [openrouter.ai](https://openrouter.ai) |

---

## `/frontend/.env` — frontend (used by Vite)

Create a `.env` file inside the `frontend/` directory:

```env
VITE_APP_PASSWORD=changeme
```

| Variable             | Required | Description                                                  |
|----------------------|----------|--------------------------------------------------------------|
| `VITE_APP_PASSWORD`  | no       | Password shown at the login gate. Leave empty to disable it. |
