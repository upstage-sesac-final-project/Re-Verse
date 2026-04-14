import { useEffect, useRef } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

export default function Home() {
  const navigate = useNavigate()
  const { isAuthenticated } = useSelector((s) => s.user)
  const mainRef = useRef(null)
  const heroRef = useRef(null)
  const titleRef = useRef(null)
  const featureRefs = useRef([])
  const progressRef = useRef(null)
  const blob1Ref = useRef(null)
  const blob2Ref = useRef(null)

  useEffect(() => {
    const ctx = gsap.context(() => {
      // 1. Top Progress Bar
      gsap.to(progressRef.current, {
        scaleX: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: mainRef.current,
          start: 'top top',
          end: 'bottom bottom',
          scrub: 0.3
        }
      })

      // 2. Hero Title Animation
      if (titleRef.current) {
        const text = titleRef.current.innerText
        titleRef.current.innerHTML = text.split('').map(c =>
          `<span class="inline-block">${c === ' ' ? '&nbsp;' : c}</span>`
        ).join('')

        gsap.from(titleRef.current.children, {
          y: 100,
          opacity: 0,
          rotateX: -90,
          stagger: 0.05,
          duration: 1.2,
          ease: 'back.out(1.7)',
          delay: 0.2
        })
      }

      // 3. Hero Sub & Blobs
      gsap.from('.hero-sub', { y: 30, opacity: 0, duration: 1, delay: 0.8, ease: 'power3.out' })
      gsap.to(blob1Ref.current, { y: 200, x: 100, scrollTrigger: { trigger: mainRef.current, scrub: 1 } })
      gsap.to(blob2Ref.current, { y: -300, x: -50, scrollTrigger: { trigger: mainRef.current, scrub: 1.5 } })

      // 4. Features & CTA
      featureRefs.current.forEach((el, i) => {
        if (el) {
          gsap.from(el, {
            scrollTrigger: { trigger: el, start: 'top 85%' },
            y: 60, opacity: 0, scale: 0.95, duration: 0.8, delay: i * 0.1
          })
        }
      })
      gsap.from('.cta-content', { scrollTrigger: { trigger: '.cta-content', start: 'top 85%' }, y: 40, opacity: 0, duration: 1 })
    }, mainRef)
    return () => ctx.revert()
  }, [])

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      {/* 배경 */}
      {/* 헤더 */}
      <header className="relative flex items-center justify-between px-6 py-5 max-w-4xl mx-auto w-full">
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-6 h-6 rounded-md flex items-center justify-center text-white font-bold text-xs" style={{ background: 'var(--accent)' }}>R</div>
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Re:Verse</span>
        </Link>
        <nav className="flex items-center gap-4">
          <Link to="/docs" className="text-xs transition-colors hover:text-white" style={{ color: 'var(--text-secondary)' }}>문서</Link>
          {isAuthenticated
            ? <Link to="/dashboard" className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>대시보드</Link>
            : <Link to="/login" className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>로그인</Link>
          }
        </nav>
      </header>

      {/* 히어로 */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 pb-24">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-center mb-4" style={{ color: 'var(--text-primary)' }}>
          채팅으로 RPG를 만드세요
        </h1>
        <p className="text-sm text-center max-w-sm mb-10 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          Re:Verse는 자연어로 RPG Maker MZ 게임을 제작하는 도구입니다.
          캐릭터, 맵, 이벤트를 대화로 만들고 바로 플레이할 수 있습니다.
        </p>

        <div className="flex items-center gap-3 mb-16">
          <button onClick={() => navigate(isAuthenticated ? '/dashboard' : '/register')}
            className="re-btn-primary px-6 py-2.5 text-sm rounded-lg font-medium"
            style={{ background: 'var(--accent)', color: '#fff' }}>
            {isAuthenticated ? '대시보드' : '시작하기'}
          </button>
          <Link to="/docs" className="px-5 py-2.5 text-sm rounded-lg font-medium transition-colors hover:bg-white/5"
            style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            가이드
          </Link>
        </div>

        {/* 기능 */}
        <div className="grid grid-cols-3 gap-px max-w-lg w-full rounded-lg overflow-hidden "
          style={{ border: '1px solid rgba(255,255,255,0.06)' }}>
          {[
            { icon: '~', label: '자연어 생성', sub: '대화로 게임 요소 생성' },
            { icon: '>', label: '즉시 플레이', sub: '생성 즉시 실행 확인' },
            { icon: '#', label: 'MZ 전 요소', sub: '캐릭터부터 이벤트까지' },
          ].map((f) => (
            <div key={f.label} className="px-4 py-5 text-center" style={{ background: 'var(--bg-secondary)' }}>
              <span className="text-lg block mb-1" style={{ color: 'var(--accent)' }}>{f.icon}</span>
              <p className="text-xs font-medium mb-0.5" style={{ color: 'var(--text-primary)' }}>{f.label}</p>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{f.sub}</p>
            </div>
          ))}
        </div>
      </main>

      {/* 풋터 */}
      <footer className="relative px-6 py-5 text-center">
        <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Re:Verse — AI RPG 제작 도구</p>
      </footer>
    </div>
  )
}
