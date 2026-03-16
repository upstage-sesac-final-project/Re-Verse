import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center h-screen bg-gray-900 text-white">
      <h1 className="text-8xl font-bold text-blue-500 mb-4">404</h1>
      <p className="text-xl text-gray-400 mb-8">페이지를 찾을 수 없습니다</p>
      <button
        onClick={() => navigate('/')}
        className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
      >
        홈으로 돌아가기
      </button>
    </div>
  )
}
