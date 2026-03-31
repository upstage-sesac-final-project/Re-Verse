import { useEffect, useState } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import * as adminApi from '../services/adminApi'

const TABS = ['개요', '유저 트렌드', '사용량', '헬스']

function StatCard({ label, value, sub }) {
  return (
    <div
      className="rounded-xl p-5 flex-1 min-w-[140px]"
      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
    >
      <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>{value}</p>
      {sub && <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{sub}</p>}
    </div>
  )
}

function PeriodToggle({ period, onChange }) {
  return (
    <div className="flex gap-1 mb-4">
      {['daily', 'monthly'].map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className="px-3 py-1 text-xs rounded-lg"
          style={{
            background: period === p ? 'var(--accent)' : 'var(--border)',
            color: period === p ? '#fff' : 'var(--text-secondary)',
          }}
        >
          {p === 'daily' ? '일별' : '월별'}
        </button>
      ))}
    </div>
  )
}

function HealthBadge({ label, ok, detail }) {
  return (
    <div
      className="rounded-xl p-5"
      style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-3 h-3 rounded-full"
          style={{ background: ok ? '#22c55e' : '#ef4444' }}
        />
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</span>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{detail}</p>
    </div>
  )
}

const chartStyle = { fontSize: 11, fill: '#999' }

export default function Admin() {
  const navigate = useNavigate()
  const { user } = useSelector((s) => s.user)
  const [tab, setTab] = useState(0)

  const [overview, setOverview] = useState(null)
  const [signups, setSignups] = useState([])
  const [logins, setLogins] = useState([])
  const [usage, setUsage] = useState([])
  const [intents, setIntents] = useState([])
  const [health, setHealth] = useState(null)

  const [signupPeriod, setSignupPeriod] = useState('daily')
  const [usagePeriod, setUsagePeriod] = useState('daily')

  useEffect(() => {
    adminApi.fetchOverview().then(setOverview).catch(() => {})
  }, [])

  useEffect(() => {
    const days = signupPeriod === 'monthly' ? 365 : 30
    adminApi.fetchSignups(signupPeriod, days).then(setSignups).catch(() => {})
    adminApi.fetchLogins(signupPeriod, days).then(setLogins).catch(() => {})
  }, [signupPeriod])

  useEffect(() => {
    const days = usagePeriod === 'monthly' ? 365 : 30
    adminApi.fetchUsage(usagePeriod, days).then(setUsage).catch(() => {})
    adminApi.fetchIntents().then(setIntents).catch(() => {})
  }, [usagePeriod])

  useEffect(() => {
    if (tab === 3) adminApi.fetchHealth().then(setHealth).catch(() => {})
  }, [tab])

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* Header */}
      <header
        className="h-14 flex items-center justify-between px-6"
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
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium ml-1"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            Admin
          </span>
        </div>
        <button
          onClick={() => navigate('/dashboard')}
          className="text-xs px-3 py-1.5 rounded-lg"
          style={{ background: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          대시보드로
        </button>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex gap-1 mb-8">
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              className="px-4 py-2 text-sm rounded-lg font-medium"
              style={{
                background: tab === i ? 'var(--accent)' : 'transparent',
                color: tab === i ? '#fff' : 'var(--text-secondary)',
              }}
            >
              {t}
            </button>
          ))}
        </div>

        {/* 개요 탭 */}
        {tab === 0 && overview && (
          <div className="flex flex-wrap gap-4">
            <StatCard label="총 유저" value={overview.total_users} />
            <StatCard label="총 프로젝트" value={overview.total_projects} />
            <StatCard label="총 대화" value={overview.total_conversations} />
            <StatCard label="성공률" value={`${(overview.success_rate * 100).toFixed(1)}%`} />
            <StatCard label="평균 응답시간" value={`${overview.avg_processing_time}s`} />
          </div>
        )}

        {/* 유저 트렌드 탭 */}
        {tab === 1 && (
          <>
            <PeriodToggle period={signupPeriod} onChange={setSignupPeriod} />
            <div className="mb-8">
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                신규 가입
              </h3>
              <div style={{ width: '100%', height: 280 }}>
                <ResponsiveContainer>
                  <BarChart data={signups}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis dataKey="date" tick={chartStyle} />
                    <YAxis tick={chartStyle} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#e60012" name="가입" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                로그인 수
              </h3>
              <div style={{ width: '100%', height: 280 }}>
                <ResponsiveContainer>
                  <BarChart data={logins}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis dataKey="date" tick={chartStyle} />
                    <YAxis tick={chartStyle} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#3b82f6" name="로그인" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}

        {/* 사용량 탭 */}
        {tab === 2 && (
          <>
            <PeriodToggle period={usagePeriod} onChange={setUsagePeriod} />
            <div className="mb-8">
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                API 사용량
              </h3>
              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                  <AreaChart data={usage}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis dataKey="date" tick={chartStyle} />
                    <YAxis tick={chartStyle} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="total" stroke="#999" fill="#3d3d3d" name="전체" />
                    <Area type="monotone" dataKey="success" stroke="#22c55e" fill="#22c55e33" name="성공" />
                    <Area type="monotone" dataKey="failed" stroke="#ef4444" fill="#ef444433" name="실패" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                Intent 분포
              </h3>
              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                  <BarChart data={intents} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#3d3d3d" />
                    <XAxis type="number" tick={chartStyle} allowDecimals={false} />
                    <YAxis type="category" dataKey="intent" tick={chartStyle} width={120} />
                    <Tooltip contentStyle={{ background: '#2d2d2d', border: '1px solid #3d3d3d', borderRadius: 8 }} />
                    <Bar dataKey="count" fill="#e60012" name="횟수" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}

        {/* 헬스 탭 */}
        {tab === 3 && health && (
          <div className="flex flex-col gap-4">
            <HealthBadge label="Database" ok={health.db.ok} detail={health.db.detail} />
            <HealthBadge label="S3 Storage" ok={health.s3.ok} detail={health.s3.detail} />
            {overview && (
              <div
                className="rounded-xl p-5"
                style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
              >
                <p className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
                  성능 지표
                </p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  평균 응답시간: {overview.avg_processing_time}s / 성공률: {(overview.success_rate * 100).toFixed(1)}%
                </p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
