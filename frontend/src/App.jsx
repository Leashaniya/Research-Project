import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ProtectedRoute from './components/ProtectedRoute';
import DashboardHome from './pages/DashboardHome';
import GuidancePage from './pages/GuidancePage';
import ModelPaperPage from './pages/ModelPaperPage';
import EssayApp from './essay-support-system/EssayApp';
import MCQStudyPlan from './pages/MCQStudyPlan';
import './App.css';

function App() {
  return (
    <Router>
      <Routes>
        {/* All services require Google sign-in before access */}
        <Route path="/" element={<ProtectedRoute />}>
          <Route index element={<DashboardHome />} />
          <Route path="ca-guidance" element={<GuidancePage />} />
          <Route path="model-paper" element={<ModelPaperPage />} />
          <Route path="essay-support/*" element={<EssayApp />} />
          <Route path="mcq-study-plan" element={<MCQStudyPlan />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
