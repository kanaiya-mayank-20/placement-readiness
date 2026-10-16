# Matchwork frontend

React + Vite client for the FastAPI backend in `../backend`.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

The client uses `http://localhost:8000` for the API by default. Set `VITE_API_URL` in a local `.env` file to use a different backend URL. Start the backend separately from `backend` with `uvicorn app.main:app --reload`.

The app supports candidate registration and sign-in, resume/GitHub analysis, ranked match details, readiness plans and feedback, company browsing, and admin job-description management.