import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import GameEditor from './pages/GameEditor'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/editor" element={<GameEditor />} />
      </Routes>
    </BrowserRouter>
  )
}
