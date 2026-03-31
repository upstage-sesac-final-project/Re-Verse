import { useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()
  const { isAuthenticated } = useSelector((s) => s.user)

  function handleStart() {
    navigate(isAuthenticated ? '/dashboard' : '/login')
  }

  return (
    <div className="flex flex-col items-center justify-center h-screen bg-gray-900 text-white">
      <h1 className="text-5xl font-bold mb-4">Re:Verse</h1>
      <p className="text-lg text-gray-400 mb-8">
        자연어로 RPG 게임을 만들어보세요
      </p>
      <button
        onClick={handleStart}
        className="px-8 py-3 bg-blue-600 text-white text-lg rounded-lg hover:bg-blue-700 transition-colors"
      >
        시작하기
      </button>
      {!isAuthenticated && (
        <p className="mt-4 text-sm text-gray-500">
          계정이 없으신가요?{' '}
          <Link to="/register" className="text-blue-400 underline">
            회원가입
          </Link>
        </p>
      )}
    </div>
  )
}
