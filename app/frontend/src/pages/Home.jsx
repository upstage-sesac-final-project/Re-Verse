import { useEffect, useRef } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate, Link } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

const FEATURES = [
  {
    icon: '✦',
    title: '자연어 명령',
    desc: '복잡한 편집기 없이 말하듯 설명하면 AI가 게임 요소를 만들어줍니다.',
  },
  {
    icon: '⟳',
    title: '즉시 미리보기',
    desc: 'AI가 생성한 캐릭터, 아이템, 맵을 바로 게임에서 확인할 수 있습니다.',
  },
  {
    icon: '◈',
    title: '다양한 요소 지원',
    desc: '캐릭터, 적, 스킬, 아이템, 맵, 이벤트 등 RPG Maker MZ 전 요소를 지원합니다.',
  },
]

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

  function handleStart() {
    navigate(isAuthenticated ? '/dashboard' : '/login')
  }

  return (
    <div ref={mainRef} className="min-h-screen overflow-x-hidden bg-[#0a0a0b] text-[#f2f2f7] selection:bg-[#ff3b5c] selection:text-white font-sans">
      <div ref={progressRef} className="fixed top-0 left-0 w-full h-1 bg-[#ff3b5c] origin-left scale-x-0 z-50"></div>

      <section ref={heroRef} className="relative h-screen flex flex-col items-center justify-center px-6 text-center z-10">
        <div className="hero-sub mb-8 inline-flex items-center justify-center w-20 h-20 rounded-[2.5rem] bg-[#ff3b5c] shadow-[0_0_50px_rgba(255,59,92,0.5)] text-white font-bold text-4xl transform hover:rotate-12 transition-transform">
          R
        </div>
        <h1
          ref={titleRef}
          className="text-7xl md:text-9xl font-black mb-8 tracking-tighter text-white drop-shadow-[0_0_30px_rgba(255,255,255,0.2)]"
        >
          Re:Verse
        </h1>
        <div className="hero-sub max-w-2xl">
          <p className="text-xl md:text-2xl text-[#8e8e93] mb-12 font-light leading-relaxed">
            당신의 상상을 현실로. <br />
            자연어 한 문장으로 시작하는 RPG 제작의 혁명.
          </p>
          <button
            onClick={handleStart}
            className="group relative px-10 py-4 text-lg bg-white text-black hover:text-white rounded-full font-bold transition-all duration-300 overflow-hidden"
          >
            <span className="relative z-10">무료로 시작하기</span>
            <div className="absolute inset-0 bg-[#ff3b5c] translate-y-full group-hover:translate-y-0 transition-transform"></div>
          </button>
        </div>
      </section>

      <section className="relative py-48 px-6 max-w-7xl mx-auto z-10">
        <h2 className="text-4xl md:text-5xl font-bold mb-24 text-center tracking-tight">더 쉽고, 더 빠르게.</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
          {FEATURES.map((f, i) => (
            <div
              key={f.title}
              ref={(el) => (featureRefs.current[i] = el)}
              className="group p-10 rounded-[2.5rem] bg-[#1c1c1e]/50 backdrop-blur-xl border border-white/5 hover:border-[#ff3b5c]/30 transition-all hover:-translate-y-4"
            >
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#2c2c2e] to-[#1c1c1e] flex items-center justify-center text-3xl mb-8 text-[#ff3b5c] group-hover:rotate-[360deg] transition-transform duration-1000">
                {f.icon}
              </div>
              <h3 className="text-2xl font-bold mb-5 group-hover:text-[#ff3b5c] transition-colors">{f.title}</h3>
              <p className="text-[#8e8e93] text-lg leading-relaxed font-light">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="relative py-60 px-6 text-center z-10">
        <div className="cta-content max-w-4xl mx-auto">
          <h2 className="text-4xl md:text-5xl font-extralight mb-8 leading-tight tracking-tight text-white/90">
            준비되셨나요? <br />
            당신의 첫 번째 맵을 <span className="font-bold text-white text-5xl md:text-7xl ml-2">만드세요.</span>
          </h2>
          {!isAuthenticated && (
            <div className="flex flex-col sm:flex-row items-center justify-center gap-8 mt-16">
              <Link to="/register" className="px-8 py-3 bg-[#ff3b5c] text-white rounded-full font-semibold hover:shadow-[0_0_30px_rgba(255,59,92,0.4)] transition-all">
                지금 시작하기
              </Link>
              <Link to="/docs" className="text-lg text-[#8e8e93] hover:text-white transition-colors border-b border-white/10 pb-1">
                가이드 둘러보기
              </Link>
            </div>
          )}
        </div>
      </section>

      <footer className="py-20 px-6 text-center border-t border-white/5 opacity-40">
        <p className="text-sm tracking-widest uppercase">© 2026 Re:Verse Project.</p>
      </footer>

      <div className="fixed top-0 left-0 w-full h-full pointer-events-none -z-10 overflow-hidden">
        <div ref={blob1Ref} className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-[#ff3b5c]/15 blur-[150px] rounded-full"></div>
        <div ref={blob2Ref} className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-blue-600/10 blur-[150px] rounded-full"></div>
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay"></div>
      </div>
    </div>
  )
}
