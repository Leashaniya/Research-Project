# Academic Assistance Platform

A unified platform providing two academic assistance services:
- **CA Guidance**: Personalized guidance, summaries, flashcards, and study recommendations
- **Model Paper**: AI-powered model exam paper generation with aligned short notes

## 📁 Project Structure

```
Research Project/
├── frontend/
│   ├── dashboard/                          # Unified Dashboard (Port 4000)
│   ├── model-paper-frontend/              # Model Paper Frontend (Port 3000)
│   └── ca-guidance-and-summarization-frontend/  # CA Guidance Frontend (Port 3333)
├── backend/
│   ├── model-paper-backend/               # Model Paper Backend (Port 8000)
│   └── ca-guidance-and-summarization-backend/   # CA Guidance Backend (Port 8001)
└── data/                                   # Shared data directory
```

## 🚀 Quick Start

### 1. Start the Dashboard (Entry Point)

The dashboard is your starting point. It provides access to both services.

```bash
cd frontend/dashboard
npm install
npm start
```

The dashboard will be available at: **http://localhost:4000**

### 2. Start Model Paper Service

**Backend:**
```bash
cd backend/model-paper-backend
# Install dependencies if needed
python -m uvicorn app.main:app --port 8000
```

**Frontend:**
```bash
cd frontend/model-paper-frontend
npm install
npm start
```

Model Paper will be available at: **http://localhost:3000**

### 3. Start CA Guidance Service

**Backend:**
```bash
cd backend/ca-guidance-and-summarization-backend
# Install dependencies if needed
python main.py
```

**Frontend:**
```bash
cd frontend/ca-guidance-and-summarization-frontend
npm install
npm run dev
```

CA Guidance will be available at: **http://localhost:3333**

## 🔧 Port Configuration

| Service | Port | URL |
|---------|------|-----|
| Dashboard | 4000 | http://localhost:4000 |
| Model Paper Frontend | 3000 | http://localhost:3000 |
| Model Paper Backend | 8000 | http://localhost:8000 |
| CA Guidance Frontend | 3333 | http://localhost:3333 |
| CA Guidance Backend | 8001 | http://localhost:8001 |

## 📋 Running All Services

To run the complete platform, you'll need 5 terminal windows:

1. **Terminal 1 - Dashboard:**
   ```bash
   cd frontend/dashboard && npm start
   ```

2. **Terminal 2 - Model Paper Backend:**
   ```bash
   cd backend/model-paper-backend && python -m uvicorn app.main:app --port 8000
   ```

3. **Terminal 3 - Model Paper Frontend:**
   ```bash
   cd frontend/model-paper-frontend && npm start
   ```

4. **Terminal 4 - CA Guidance Backend:**
   ```bash
   cd backend/ca-guidance-and-summarization-backend && python main.py
   ```

5. **Terminal 5 - CA Guidance Frontend:**
   ```bash
   cd frontend/ca-guidance-and-summarization-frontend && npm run dev
   ```

## 🎯 Usage Flow

1. **Start with Dashboard**: Navigate to http://localhost:4000
2. **Choose a Service**: Click either "CA Guidance" or "Model Paper" button
3. **Use the Service**: You'll be redirected to the respective frontend application

## 🔐 Environment Variables

### Dashboard
Create `frontend/dashboard/.env` (optional):
```env
PORT=4000
REACT_APP_CA_GUIDANCE_URL=http://localhost:3333
REACT_APP_MODEL_PAPER_URL=http://localhost:3000
```

### CA Guidance Frontend
Create `frontend/ca-guidance-and-summarization-frontend/.env`:
```env
VITE_API_URL=http://localhost:8001
```

### Model Paper Frontend
The frontend connects to `http://localhost:8000` by default (configured in `src/App.js`).

## 📦 Dependencies

Each frontend and backend has its own `package.json` or `requirements.txt`. Install dependencies in each directory:

- **Frontend projects**: `npm install`
- **Backend projects**: Follow Python dependency installation (pip/uv/poetry)

## 🛠️ Development

### Dashboard Customization

The dashboard can be customized by:
- Modifying `frontend/dashboard/src/App.js` for button behavior
- Updating `frontend/dashboard/src/App.css` for styling
- Changing environment variables for different URLs

### Service Independence

Each service (CA Guidance and Model Paper) operates independently:
- Separate frontends and backends
- No shared state between services
- Can be developed and deployed separately

## 📝 Notes

- Ensure all backends are running before using their respective frontends
- The dashboard is a simple redirect interface - it doesn't require backend services
- Port conflicts: If ports are already in use, update the configuration files accordingly

## 🤝 Contributing

This is an integrated platform combining:
- **Leasha's Model Paper Generator** (model-paper-frontend/backend)
- **Janu's CA Guidance System** (ca-guidance-and-summarization-frontend/backend)

Both systems maintain their independent functionality while being accessible through a unified dashboard.
