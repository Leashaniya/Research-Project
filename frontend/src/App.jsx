import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import DashboardHome from './pages/DashboardHome';
import GuidancePage from './pages/GuidancePage';
import ModelPaperPage from './pages/ModelPaperPage';
import MCQStudyPlan from './pages/MCQStudyPlan';
import './App.css';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/ca-guidance" element={<GuidancePage />} />
        <Route path="/model-paper" element={<ModelPaperPage />} />
        <Route path="/mcq-study-plan" element={<MCQStudyPlan />} />
      </Routes>
    </Router>
  );
}

export default App;
