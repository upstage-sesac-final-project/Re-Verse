import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { fetchProjects, createProject, deleteProject } from '../store/gameSlice'
import { setCurrentProject } from '../store/gameSlice'
import { logoutUser } from '../store/userSlice'
import Modal from '../components/common/Modal'

export default function Dashboard() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { user } = useSelector((s) => s.user)
  const { projects, isLoading } = useSelector((s) => s.game)

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [createError, setCreateError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)

  useEffect(() => {
    dispatch(fetchProjects())
  }, [dispatch])

  async function handleCreate(e) {
    e.preventDefault()
    if (!newName.trim()) return
    setCreateError('')
    const result = await dispatch(createProject({ name: newName.trim(), description: newDesc.trim() }))
    if (createProject.rejected.match(result)) {
      setCreateError(result.payload || '프로젝트 생성에 실패했습니다.')
    } else {
      setCreating(false)
      setNewName('')
      setNewDesc('')
    }
  }

  function handleEdit(project) {
    dispatch(setCurrentProject(project))
    navigate(`/editor/${String(project.id)}`)
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return
    await dispatch(deleteProject(deleteTarget.id))
    setDeleteTarget(null)
  }

  async function handleLogout() {
    await dispatch(logoutUser())
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* Header */}
      <header
        className="h-14 flex items-center justify-between px-6"
        style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            R
          </div>
          <span className="font-semibold text-lg" style={{ color: 'var(--text-primary)' }}>
            Re:Verse
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {user?.username}
          </span>
          <button
            onClick={handleLogout}
            className="text-xs px-3 py-1.5 rounded-lg"
            style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            로그아웃
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            내 프로젝트
          </h1>
          <button
            onClick={() => setCreating(true)}
            disabled={projects.length >= 3}
            className="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            + 새 프로젝트
          </button>
        </div>

        {projects.length >= 3 && (
          <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>
            프로젝트는 최대 3개까지 생성할 수 있습니다.
          </p>
        )}

        {/* 새 프로젝트 폼 */}
        {creating && (
          <form
            onSubmit={handleCreate}
            className="rounded-xl p-5 mb-4"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
          >
            <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
              새 프로젝트
            </h2>
            <input
              type="text"
              placeholder="프로젝트 이름"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm outline-none mb-2"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            <input
              type="text"
              placeholder="설명 (선택)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none mb-3"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            {createError && (
              <p className="text-xs mb-2" style={{ color: '#f87171' }}>
                {createError}
              </p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setCreating(false); setCreateError('') }}
                className="px-3 py-1.5 text-sm rounded-lg"
                style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                취소
              </button>
              <button
                type="submit"
                className="px-3 py-1.5 text-sm rounded-lg font-medium"
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                만들기
              </button>
            </div>
          </form>
        )}

        {/* 프로젝트 목록 */}
        {isLoading ? (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            불러오는 중...
          </p>
        ) : projects.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center"
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
          >
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              아직 프로젝트가 없습니다. 새 프로젝트를 만들어보세요!
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {projects.map((project) => (
              <div
                key={project.id}
                className="rounded-xl p-5 flex items-center justify-between"
                style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
              >
                <div>
                  <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                    {project.name}
                  </h3>
                  {project.description && (
                    <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                      {project.description}
                    </p>
                  )}
                  <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                    수정: {new Date(project.updated_at).toLocaleDateString('ko-KR')}
                  </p>
                </div>
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => handleEdit(project)}
                    className="px-3 py-1.5 text-xs rounded-lg font-medium"
                    style={{ background: 'var(--accent)', color: '#fff' }}
                  >
                    편집
                  </button>
                  <button
                    onClick={() => setDeleteTarget(project)}
                    className="px-3 py-1.5 text-xs rounded-lg"
                    style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
                  >
                    삭제
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {deleteTarget && (
        <Modal
          title="프로젝트 삭제"
          message={`"${deleteTarget.name}" 프로젝트를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
          confirmLabel="삭제"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
