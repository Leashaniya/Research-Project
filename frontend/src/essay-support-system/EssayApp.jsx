import { Routes, Route } from 'react-router-dom';
import { SessionProvider } from './context/SessionContext';
import Layout from './components/Layout';
import Home from './pages/Home';
import Practice from './pages/Practice';
import Analytics from './pages/Analytics';
import NotFound from './pages/NotFound';
import './essay-support.css';

export default function EssayApp() {
  return (
    <SessionProvider>
      <div className="essay-support-root">
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="practice" element={<Practice />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </div>
    </SessionProvider>
  );
}
