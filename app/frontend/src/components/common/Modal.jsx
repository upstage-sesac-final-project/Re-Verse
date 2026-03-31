export default function Modal({ title, message, errorMessage, confirmLabel = '확인', cancelLabel = '취소', onConfirm, onCancel, loading = false }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={!loading ? onCancel : undefined} />
      <div
        className="relative rounded-xl p-6 w-80 shadow-xl"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
      >
        <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h3>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {message}
        </p>
        {errorMessage && (
          <p className="text-xs mt-2" style={{ color: '#f87171' }}>
            {errorMessage}
          </p>
        )}
        <div className="mt-5" />
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg disabled:opacity-50"
            style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg font-medium disabled:opacity-50"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {loading ? '처리 중...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
