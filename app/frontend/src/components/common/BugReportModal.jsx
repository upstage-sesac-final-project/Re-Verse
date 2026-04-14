import { useEffect, useState } from 'react'
import { submitBugReport } from '../../services/bugReportApi'

export default function BugReportModal({ onClose }) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [loading, onClose])

  async function handleSubmit() {
    const text = content.trim()
    if (!text) {
      setError('내용을 입력해주세요.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await submitBugReport(text)
      setDone(true)
      setTimeout(() => onClose(), 1200)
    } catch (e) {
      setError(e?.message || '전송에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={!loading ? onClose : undefined} />
      <div
        className="relative rounded-xl p-6 w-96 shadow-xl"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
      >
        <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          버그 리포트
        </h3>
        <p className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
          버그에 대한 상세한 내용을 작성해주세요.
        </p>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={loading || done}
          rows={6}
          maxLength={4000}
          placeholder="언제, 어디서, 어떤 동작을 할 때 문제가 발생했는지 적어주세요."
          className="w-full text-sm rounded-lg p-3 outline-none resize-none"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />
        {error && (
          <p className="text-xs mt-2" style={{ color: '#f87171' }}>
            {error}
          </p>
        )}
        {done && (
          <p className="text-xs mt-2" style={{ color: '#4ade80' }}>
            전송되었습니다. 감사합니다!
          </p>
        )}
        <div className="mt-5 flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg disabled:opacity-50"
            style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || done}
            className="px-4 py-2 text-sm rounded-lg font-medium disabled:opacity-50"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {loading ? '전송 중...' : '전송'}
          </button>
        </div>
      </div>
    </div>
  )
}
