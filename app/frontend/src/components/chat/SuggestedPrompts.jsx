const PROMPTS = [
  '용사 캐릭터를 만들어줘. 이름은 아르테, HP 500, 힘 80.',
  '불의 마법사 보스 적을 만들어줘.',
  '초원 마을 맵을 만들어줘.',
  '체력 포션 아이템을 추가해줘.',
  '현재 캐릭터 목록을 보여줘.',
]

export default function SuggestedPrompts({ onSelect }) {
  return (
    <div className="flex-1 flex flex-col justify-center p-4">
      <p className="text-xs font-medium mb-3" style={{ color: 'var(--text-secondary)' }}>
        예시 명령어를 눌러 시작하세요
      </p>
      <div className="flex flex-col gap-2">
        {PROMPTS.map((prompt, i) => (
          <button
            key={i}
            onClick={() => onSelect(prompt)}
            className="re-card text-left text-xs px-3 py-2.5 rounded-lg transition-opacity"
            style={{
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}
