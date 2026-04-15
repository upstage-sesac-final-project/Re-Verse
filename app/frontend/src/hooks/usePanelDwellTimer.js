import { useCallback, useEffect, useRef } from 'react'
import posthog from 'posthog-js'

const TAB_NAME_MAP = {
  play: 'play_panel',
  map: 'map_viewer',
  data: 'game_data',
}

export function usePanelDwellTimer({ activePanel, projectId }) {
  const panelRef = useRef(activePanel)
  const startedAtRef = useRef(Date.now())
  const lastSentTimeRef = useRef(0)

  const sendToPostHog = useCallback((panel, durationMs) => {
    const now = Date.now()
    if (!panel || durationMs < 1000 || now - lastSentTimeRef.current < 500) return

    const mappedPanelName = TAB_NAME_MAP[panel] || panel
    posthog.capture('panel_stay_time', {
      panel_name: mappedPanelName,
      duration_ms: durationMs,
      duration_seconds: Math.round(durationMs / 1000),
      project_id: String(projectId || 'unknown'),
    })

    lastSentTimeRef.current = now
  }, [projectId])

  useEffect(() => {
    const now = Date.now()
    if (panelRef.current !== activePanel) {
      sendToPostHog(panelRef.current, now - startedAtRef.current)
      panelRef.current = activePanel
      startedAtRef.current = now
    }
  }, [activePanel, sendToPostHog])

  useEffect(() => {
    const flush = () => {
      sendToPostHog(panelRef.current, Date.now() - startedAtRef.current)
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flush()
      } else {
        startedAtRef.current = Date.now()
      }
    }

    window.addEventListener('beforeunload', flush)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      flush()
      window.removeEventListener('beforeunload', flush)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [sendToPostHog])
}
