export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-3 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full inline-block animate-bounce"
          style={{
            background: 'var(--text-secondary)',
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
    </div>
  )
}
