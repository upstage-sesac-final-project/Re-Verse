export default function Header() {
  return (
    <header
      className="h-14 flex items-center justify-between px-6 flex-shrink-0"
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
      <span
        className="text-xs px-2 py-1 rounded-full font-medium"
        style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
      >
        Beta
      </span>
    </header>
  )
}
