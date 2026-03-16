import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import GameEditor from './pages/GameEditor'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/editor" element={<GameEditor />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}
