import { useNavigate } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center h-screen bg-gray-900 text-white">
      <h1 className="text-5xl font-bold mb-4">Re:Verse</h1>
      <p className="text-lg text-gray-400 mb-8">
        자연어로 RPG 게임을 만들어보세요
      </p>
      <button
        onClick={() => navigate('/editor')}
        className="px-8 py-3 bg-blue-600 text-white text-lg rounded-lg hover:bg-blue-700 transition-colors"
      >
        시작하기
      </button>
    </div>
  )
}
