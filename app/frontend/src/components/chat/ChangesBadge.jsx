import { useState } from 'react'

export default function ChangesBadge({ changes }) {
  const [isOpen, setIsOpen] = useState(false)

  if (!changes || changes.length === 0) return null

  const successCount = changes.filter((c) => c.success).length
  const failCount = changes.length - successCount

  return (
    <div className="mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-2 hover:opacity-80"
      >
        <span>변경 {changes.length}건</span>
        {successCount > 0 && (
          <span
            className="px-1.5 py-0.5 rounded-full"
            style={{ background: '#1a3a2a', color: '#4caf82' }}
          >
            ✓ {successCount}
          </span>
        )}
        {failCount > 0 && (
          <span
            className="px-1.5 py-0.5 rounded-full"
            style={{ background: '#3a1a1a', color: '#e05555' }}
          >
            ✗ {failCount}
          </span>
        )}
        <span>{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <ul className="mt-2 space-y-1 pl-1">
          {changes.map((c) => (
            <li key={c.step_id} className="flex items-start gap-2">
              <span style={{ color: c.success ? '#4caf82' : '#e05555', flexShrink: 0 }}>
                {c.success ? '✓' : '✗'}
              </span>
              <div>
                <span style={{ color: 'var(--text-primary)' }}>{c.tool_name}</span>
                {c.description && (
                  <span className="ml-1" style={{ color: 'var(--text-secondary)' }}>
                    — {c.description}
                  </span>
                )}
                {c.result_summary && (
                  <div style={{ color: 'var(--text-secondary)' }}>{c.result_summary}</div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
