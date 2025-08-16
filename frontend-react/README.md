# MC Admin Frontend (React)

A React-based frontend application for MC Admin, built with Ant Design and Tailwind CSS.

## Features

- **Modern React**: Built with React 18, TypeScript, and Vite
- **Ant Design**: Professional UI components
- **Tailwind CSS**: Utility-first CSS framework for custom styling
- **State Management**: Zustand for simple and scalable state management
- **API Integration**: Axios for HTTP requests with React Query for data fetching
- **Routing**: React Router for client-side navigation
- **Authentication**: JWT-based authentication with persistent storage

## Tech Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **UI Library**: Ant Design 5
- **CSS Framework**: Tailwind CSS
- **State Management**: Zustand
- **Data Fetching**: TanStack React Query + Axios
- **Routing**: React Router Dom
- **Code Quality**: ESLint + TypeScript strict mode

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── layout/         # Layout components (Header, Sidebar)
│   └── overview/       # Overview page specific components
├── hooks/              # Custom React hooks for API calls
├── pages/              # Page components
│   └── server/         # Server management pages
├── stores/             # Zustand store definitions
├── types/              # TypeScript type definitions
├── utils/              # Utility functions (API config, etc.)
├── App.tsx             # Main application component
├── main.tsx            # Application entry point
└── index.css           # Global styles
```

## Getting Started

### Prerequisites

- Node.js 18 or higher
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Copy environment file:
```bash
cp .env.local.example .env.local
```

3. Update the API base URL in `.env.local`:
```
VITE_API_BASE_URL=http://localhost:5678/api
```

### Development

Start the development server:
```bash
npm run dev
```

The application will be available at `http://localhost:3000`.

### Building

Build for production:
```bash
npm run build
```

### Preview

Preview the production build:
```bash
npm run preview
```

## API Integration

The application communicates with the MC Admin backend API. Make sure the backend is running on the configured port (default: 5678).

## Authentication

The app supports two login methods:
1. **Password Login**: Traditional username/password authentication
2. **Code Login**: WebSocket-based dynamic code authentication

Authentication state is persisted in localStorage and automatically restored on app reload.

## Available Routes

- `/` - Home page
- `/login` - Authentication page
- `/overview` - Server overview with metrics and server list
- `/backups` - Backup management
- `/server/new` - Create new server
- `/server/:id` - Server details
- `/server/:id/players` - Player management
- `/server/:id/files` - File management
- `/server/:id/whitelist` - Whitelist management
- `/server/:id/compose` - Server configuration
- `/server/:id/archive` - Server archive/download

## Contributing

1. Follow the existing code style
2. Use TypeScript for all new code
3. Add proper type definitions
4. Test your changes thoroughly
