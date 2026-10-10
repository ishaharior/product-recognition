import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import AboutPage from './pages/AboutPage';
import CataloguePage from './pages/CataloguePage';
import HistoryPage from './pages/HistoryPage';
import LiveScannerPage from './pages/LiveScannerPage';
import OverviewPage from './pages/OverviewPage';
import StatusPage from './pages/StatusPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/scanner" element={<LiveScannerPage />} />
        <Route path="/catalogue" element={<CataloguePage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
