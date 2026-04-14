import { useEffect, useRef, useState } from 'react'
import { submitBugReport } from '../../services/bugReportApi'

const MAX_IMAGE_BYTES = 15 * 1024 * 1024

export default function BugReportModal({ onClose }) {
  const [content, setContent] = useState('')
  const [image, setImage] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [loading, onClose])

  useEffect(() => {
    if (!image) {
      setPreviewUrl('')
      return
    }
    const url = URL.createObjectURL(image)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [image])

  function pickImage(file) {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('이미지 파일만 첨부할 수 있습니다.')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError('이미지가 너무 큽니다 (최대 15MB).')
      return
    }
    setError('')
    setImage(file)
  }

  function handleFileChange(e) {
    pickImage(e.target.files?.[0])
  }

  function handlePaste(e) {
    const item = Array.from(e.clipboardData?.items || []).find((i) => i.type.startsWith('image/'))
    if (item) {
      e.preventDefault()
      pickImage(item.getAsFile())
    }
  }

  function clearImage() {
    setImage(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleSubmit() {
    const text = content.trim()
    if (!text) {
      setError('내용을 입력해주세요.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await submitBugReport({ content: text, image })
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
        className="relative rounded-xl p-6 w-96 shadow-xl max-h-[90vh] overflow-y-auto"
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
          onPaste={handlePaste}
          disabled={loading || done}
          rows={6}
          maxLength={4000}
          placeholder="언제, 어디서, 어떤 동작을 할 때 문제가 발생했는지 적어주세요. (이미지 붙여넣기 가능)"
          className="w-full text-sm rounded-lg p-3 outline-none resize-none"
          style={{
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        />

        <div className="mt-3">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            disabled={loading || done}
            className="hidden"
          />
          {!image ? (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={loading || done}
              className="text-xs px-3 py-1.5 rounded-lg disabled:opacity-50"
              style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              📎 이미지 추가
            </button>
          ) : (
            <div className="space-y-2">
              <img
                src={previewUrl}
                alt="첨부 미리보기"
                className="max-h-40 rounded-lg"
                style={{ border: '1px solid var(--border)' }}
              />
              <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <span className="truncate flex-1">{image.name} ({(image.size / 1024).toFixed(0)} KB)</span>
                <button
                  type="button"
                  onClick={clearImage}
                  disabled={loading || done}
                  className="px-2 py-1 rounded disabled:opacity-50"
                  style={{ background: 'var(--border)' }}
                >
                  제거
                </button>
              </div>
            </div>
          )}
        </div>

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
