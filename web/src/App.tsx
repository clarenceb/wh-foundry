import { Routes, Route } from 'react-router-dom';
import FullAppPage from './pages/FullAppPage';
import WidgetPage from './pages/WidgetPage';
import EmbedPage from './pages/EmbedPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<FullAppPage />} />
      <Route path="/widget" element={<WidgetPage />} />
      <Route path="/embed" element={<EmbedPage />} />
    </Routes>
  );
}
