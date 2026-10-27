# RescueMesh AI — Live deployment links

- **Live React frontend (Vercel):** https://rescue-mesh-ai-195l.vercel.app/
- **Live FastAPI backend (Render):** https://rescuemeshai-mdlk.onrender.com/
- **Interactive API documentation:** https://rescuemeshai-mdlk.onrender.com/docs
- **Health check:** https://rescuemeshai-mdlk.onrender.com/api/health

## Deployment configuration

The frontend is configured to use the deployed Render API by default. The Vite production environment is set in `frontend/.env.production`.

For local development, create `frontend/.env.local` with:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

The backend CORS configuration includes the Vercel frontend origin. Redeploy the backend after pushing the `main.py` CORS change, then redeploy the frontend after pushing the frontend changes.

## Important

These are prototype links. Mission records are stored in backend process memory and may disappear when the Render service restarts. AI output, hospital listings, routes, and mission decisions require human verification. This app does not contact emergency services or dispatch responders.
