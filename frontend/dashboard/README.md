# Academic Assistance Dashboard

A unified dashboard that provides access to two academic assistance services:
- **CA Guidance**: Personalized guidance, summaries, and flashcards
- **Model Paper**: AI-powered model exam paper generation

## Getting Started

### Installation

```bash
npm install
```

### Running the Dashboard

```bash
npm start
```

The dashboard will run on [http://localhost:4000](http://localhost:4000)

### Environment Variables

Create a `.env` file in the dashboard directory to customize frontend URLs:

```env
REACT_APP_CA_GUIDANCE_URL=http://localhost:3333
REACT_APP_MODEL_PAPER_URL=http://localhost:3000
```

## Features

- **Modern UI**: Clean, responsive design with smooth animations
- **Easy Navigation**: One-click access to both services
- **Responsive**: Works on desktop, tablet, and mobile devices

## Port Configuration

- Dashboard: Port 4000
- CA Guidance Frontend: Port 3333
- Model Paper Frontend: Port 3000
