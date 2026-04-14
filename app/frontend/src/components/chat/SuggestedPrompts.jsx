const CATEGORIES = [
  {
    label: '캐릭터',
    prompts: [
      '용사 캐릭터를 만들어줘. 이름은 아르테, HP 500, 힘 80.',
      '현재 캐릭터 목록을 보여줘.',
    ],
  },
  {
    label: '전투',
    prompts: [
      '불의 마법사 보스 적을 만들어줘.',
    ],
  },
  {
    label: '월드',
    prompts: [
      '체력 포션 아이템을 추가해줘.',
    ],
  },
]

export default function SuggestedPrompts({ onSelect }) {
  return (
    <div className="flex-1 flex flex-col justify-start p-4 pt-6 overflow-y-auto">
      <p className="text-xs mb-1" style={{ color: 'var(--text-primary)' }}>무엇을 만들까요?</p>
      <p className="text-xs mb-4" style={{ color: 'var(--text-secondary)' }}>예시를 눌러 시작하거나 직접 입력하세요</p>
      <div className="flex flex-col gap-3">
        {CATEGORIES.map((cat) => (
          <div key={cat.label}>
            <p className="text-xs font-medium mb-1.5 px-1" style={{ color: 'var(--text-secondary)' }}>{cat.label}</p>
            <div className="flex flex-col gap-1">
              {cat.prompts.map((prompt, i) => (
                <button key={i} onClick={() => onSelect(prompt)}
                  className="re-card text-left text-xs px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
