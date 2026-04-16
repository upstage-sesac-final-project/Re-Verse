import { useEffect, useRef } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'
import gsap from 'gsap'

export default function Home() {
  const navigate = useNavigate()
  const { isAuthenticated } = useSelector((s) => s.user)

  const plyRef = useRef(null)
  const uniRef = useRef(null)
  const plyWrapRef = useRef(null)
  const uniWrapRef = useRef(null)
  const midRef = useRef(null)
  const midDot1Ref = useRef(null)
  const midDot2Ref = useRef(null)
  const reRef = useRef(null)
  const verseRef = useRef(null)
  const brandRowRef = useRef(null)
  const taglineRef = useRef(null)
  const heroScopeRef = useRef(null)

  useEffect(() => {
    const root = heroScopeRef.current
    if (!root) return

    const ctx = gsap.context(() => {
      const ply = plyRef.current
      const uni = uniRef.current
      const plyWrap = plyWrapRef.current
      const uniWrap = uniWrapRef.current
      const mid = midRef.current
      const dot1 = midDot1Ref.current
      const dot2 = midDot2Ref.current
      const re = reRef.current
      const verse = verseRef.current
      const row = brandRowRef.current
      const tagline = taglineRef.current

      if (!ply || !uni || !plyWrap || !uniWrap || !mid || !dot1 || !dot2 || !re || !verse || !row) return

      // 가운데 콜론은 시작부터 빨간 점 2개를 고정
      dot1.style.backgroundColor = 'var(--accent)'
      dot2.style.backgroundColor = 'var(--accent)'
      gsap.set(dot1, { opacity: 1, scale: 1, xPercent: -50, yPercent: -50, left: '50%', top: '50%', x: 0, y: '-0.14em' })
      gsap.set(dot2, { opacity: 1, scale: 1, xPercent: -50, yPercent: -50, left: '50%', top: '50%', x: 0, y: '0.14em' })

      gsap.set([plyWrap, uniWrap], { width: 'auto', maxWidth: 'none', overflow: 'visible' })
      // from() + kill() 조합은 개발 모드에서 opacity:0에 고정될 수 있어 to()로 통일
      gsap.set(row, { opacity: 0, y: 28, gap: '0.12rem' })
      gsap.set([ply, uni], { opacity: 0, y: 10 })
      if (tagline) gsap.set(tagline, { opacity: 0, y: 12 })

      const tl = gsap.timeline({ defaults: { ease: 'power2.out' } })

      tl.to(row, { opacity: 1, y: 0, duration: 0.75, ease: 'power2.out' })
        .to([ply, uni], { opacity: 1, y: 0, duration: 0.55, stagger: 0.12, ease: 'power2.out' }, '-=0.38')

      // ply / Uni — 길게 스르륵 (위치 거의 고정, 굵기 변화 없음)
      tl.to(
        [ply, uni],
        {
          opacity: 0,
          x: (idx) => (idx === 0 ? 6 : -6),
          duration: 1.35,
          stagger: 0.16,
          ease: 'sine.out',
        },
        '+=0.6'
      )
        .set([plyWrap, uniWrap], {
          width: (idx, target) => `${target.offsetWidth}px`,
          maxWidth: (idx, target) => `${target.offsetWidth}px`,
          minWidth: (idx, target) => `${target.offsetWidth}px`,
          overflow: 'hidden',
        })
        .to(
          [plyWrap, uniWrap],
          {
            width: 0,
            maxWidth: 0,
            minWidth: 0,
            marginLeft: 0,
            marginRight: 0,
            paddingLeft: 0,
            paddingRight: 0,
            duration: 1.25,
            ease: 'sine.inOut',
          },
          '<+0.14'
        )
        .fromTo(
          re,
          { x: '-0.12em' },
          {
            x: 0,
            duration: 1.25,
            ease: 'power4.out',
          },
          '<'
        )
        .fromTo(
          verse,
          { x: '0.12em' },
          {
            x: 0,
            duration: 1.25,
            ease: 'power4.out',
          },
          '<'
        )

      if (tagline) {
        tl.to(tagline, { opacity: 1, y: 0, duration: 0.65, ease: 'power2.out' }, '-=0.35')
      }
    }, root)

    return () => ctx.revert()
  }, [])

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <header className="relative flex items-center justify-between px-6 py-5 max-w-4xl mx-auto w-full">
        <Link to="/" className="flex items-center gap-2 group">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center text-white font-bold text-xs"
            style={{ background: 'var(--accent)' }}
          >
            R
          </div>
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            Re:Verse
          </span>
        </Link>
        <nav className="flex items-center gap-4">
          <Link
            to="/docs"
            className="text-xs transition-colors hover:text-white"
            style={{ color: 'var(--text-secondary)' }}
          >
            가이드
          </Link>
          {isAuthenticated ? (
            <Link to="/dashboard" className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
              대시보드
            </Link>
          ) : (
            <Link to="/login" className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
              로그인
            </Link>
          )}
        </nav>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 pb-16">
        <div
          ref={heroScopeRef}
          className="w-full max-w-2xl mx-auto flex flex-col items-center mb-10 min-h-[9rem] sm:min-h-[10rem]"
        >
          <div
            ref={brandRowRef}
            className="flex flex-nowrap items-baseline justify-center text-[clamp(1.35rem,5vw,3.75rem)] font-bold tracking-tight select-none px-2 max-w-full overflow-x-auto md:overflow-visible [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            style={{ color: 'var(--text-primary)', gap: '0.12rem' }}
            aria-label="Re:Verse 브랜드 — Reply와 Universe에서"
          >
            <span className="inline-flex items-baseline">
              <span ref={reRef}>Re</span>
              <span ref={plyWrapRef} className="inline-block align-baseline overflow-visible">
                <span
                  ref={plyRef}
                  className="inline-block text-[0.95em] whitespace-nowrap [transform:translateZ(0)]"
                >
                  ply
                </span>
              </span>
            </span>

            <span
              ref={midRef}
              className="relative inline-block shrink-0 self-center mx-0.5 sm:mx-1 align-middle"
              style={{ width: '0.42em', height: '0.85em', minWidth: 14, minHeight: 22 }}
              aria-hidden
            >
              <span
                ref={midDot1Ref}
                className="absolute rounded-full [transform:translateZ(0)]"
                style={{
                  width: '0.2em',
                  height: '0.2em',
                  minWidth: 5,
                  minHeight: 5,
                  left: '50%',
                  top: '50%',
                  background: 'rgba(255, 255, 255, 0.92)',
                }}
              />
              <span
                ref={midDot2Ref}
                className="absolute rounded-full [transform:translateZ(0)]"
                style={{
                  width: '0.2em',
                  height: '0.2em',
                  minWidth: 5,
                  minHeight: 5,
                  left: '50%',
                  top: '50%',
                  background: 'var(--accent)',
                  opacity: 0,
                }}
              />
            </span>

            <span className="inline-flex items-baseline">
              <span ref={uniWrapRef} className="inline-block align-baseline overflow-visible">
                <span
                  ref={uniRef}
                  className="inline-block text-[0.95em] whitespace-nowrap [transform:translateZ(0)]"
                >
                  Uni
                </span>
              </span>
              <span ref={verseRef} className="inline-block font-bold">
                Verse
              </span>
            </span>
          </div>

          <p
            ref={taglineRef}
            className="mt-6 text-center text-xs sm:text-sm max-w-md leading-relaxed px-2"
            style={{ color: 'var(--text-secondary)' }}
          >
            <span className="font-medium" style={{ color: 'var(--accent)' }}>
              Re:Verse
            </span>
            — Reply(대답하다)와 Universe(세계관)의 합성어,
            <br className="hidden sm:block" /> 세상을 뒤집는다는{' '}
            <em className="not-italic font-semibold" style={{ color: 'var(--accent)' }}>
              Reverse
            </em>
            의 뜻도 담았습니다.
          </p>
        </div>

        <h1
          className="text-2xl sm:text-3xl font-bold tracking-tight text-center mb-3"
          style={{ color: 'var(--text-primary)' }}
        >
          채팅으로 RPG를 만드세요
        </h1>
        <p
          className="text-sm text-center max-w-sm mb-10 leading-relaxed"
          style={{ color: 'var(--text-secondary)' }}
        >
          Re:Verse는 자연어로 RPG Maker MZ 게임을 제작하는 도구입니다. 캐릭터, 맵, 이벤트를 대화로 만들고 바로
          플레이할 수 있습니다.
        </p>

        <div className="flex items-center gap-3 mb-16">
          <button
            type="button"
            onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="re-btn-primary px-6 py-2.5 text-sm rounded-lg font-medium"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {isAuthenticated ? '대시보드' : '시작하기'}
          </button>
          <Link
            to="/docs"
            className="px-5 py-2.5 text-sm rounded-lg font-medium transition-colors hover:bg-white/5"
            style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
          >
            가이드
          </Link>
        </div>

        <div
          className="grid grid-cols-1 sm:grid-cols-3 gap-px max-w-lg w-full rounded-lg overflow-hidden"
          style={{ border: '1px solid rgba(255, 255, 255, 0.06)' }}
        >
          {[
            { icon: '~', label: '자연어 생성', sub: '대화로 게임 요소 생성' },
            { icon: '>', label: '즉시 플레이', sub: '생성 즉시 실행 확인' },
            { icon: '#', label: 'MZ 전 요소', sub: '캐릭터부터 이벤트까지' },
          ].map((f) => (
            <div key={f.label} className="px-4 py-5 text-center" style={{ background: 'var(--bg-secondary)' }}>
              <span className="text-lg block mb-1" style={{ color: 'var(--accent)' }}>
                {f.icon}
              </span>
              <p className="text-xs font-medium mb-0.5" style={{ color: 'var(--text-primary)' }}>
                {f.label}
              </p>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {f.sub}
              </p>
            </div>
          ))}
        </div>
      </main>

      <footer className="relative px-6 py-5 text-center">
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          Re:Verse — AI RPG 제작 도구
        </p>
      </footer>
    </div>
  )
}
