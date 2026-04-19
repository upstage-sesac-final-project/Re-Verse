import { useState } from 'react'

const SUGGESTED_PROMPTS = [
  { label: '중세 판타지', full: '중세 판타지 세계에서 용사가 마왕을 쓰러뜨리는 RPG' },
  { label: '해적 모험', full: '해적 왕국을 배경으로 한 모험 RPG. 주인공이 전설의 보물을 찾는 이야기' },
  { label: '사이버펑크', full: '미래 도시의 사이버펑크 RPG. 해커 주인공이 거대 기업에 맞서 싸운다' },
  { label: '마법사 왕국', full: '마법사 왕국에서 어둠의 마왕을 물리치는 짧은 RPG' },
]

export default function GenerationForm({ onSubmit, isLoading }) {
  const [prompt, setPrompt] = useState('')
  const [playtime, setPlaytime] = useState(7)

  function handleSubmit(e) {
    e.preventDefault()
    if (!prompt.trim() || isLoading) return
    onSubmit({ prompt: prompt.trim(), options: { playtime_minutes: playtime } })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label className="block text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
          게임 설명
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={"어떤 게임을 만들고 싶은지 자유롭게 설명해주세요...\n(현재는 RPG 장르만 지원하지만, 어떤 주제든 멋진 RPG로 만들어드려요 !)"}
          rows={4}
          maxLength={1000}
          required
          disabled={isLoading}
          className="w-full rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            '--tw-ring-color': 'var(--accent)',
          }}
        />
        <div className="flex justify-between mt-1">
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTED_PROMPTS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => setPrompt(p.full)}
                disabled={isLoading}
                title={p.full}
                className="text-xs px-2.5 py-1 rounded-lg transition-colors hover:border-white/20"
                style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {prompt.length}/1000
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <label className="text-sm font-medium whitespace-nowrap" style={{ color: 'var(--text-secondary)' }}>
          플레이타임
        </label>
        <input
          type="range"
          min={5}
          max={15}
          step={1}
          value={playtime}
          onChange={(e) => setPlaytime(Number(e.target.value))}
          disabled={isLoading}
          className="flex-1"
          style={{ accentColor: 'var(--accent)' }}
        />
        <span className="text-sm font-bold w-12 text-right" style={{ color: 'var(--text-primary)' }}>
          {playtime}분
        </span>
      </div>

      <button
        type="submit"
        disabled={!prompt.trim() || isLoading}
        className="w-full py-3 rounded-lg font-semibold text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ background: 'var(--accent)', color: '#fff' }}
      >
        {isLoading ? '생성 중...' : '게임 생성 시작'}
      </button>
    </form>
  )
}
