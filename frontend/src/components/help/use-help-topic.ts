import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { loadTopic, type HelpDocument } from '@/help/loader'

/**
 * A topic's document in the reader's language, or null while it loads / when it
 * does not exist. Guards against a slow load landing after the reader has already
 * moved on to another topic.
 */
export function useHelpTopic(id: string | undefined): { doc: HelpDocument | null; loading: boolean } {
  const { i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const [state, setState] = useState<{ key: string; doc: HelpDocument | null } | null>(null)
  const key = id ? `${language}:${id}` : ''

  useEffect(() => {
    if (!id) return
    let active = true
    loadTopic(id, language)
      .then((doc) => active && setState({ key, doc }))
      .catch(() => active && setState({ key, doc: null }))
    return () => {
      active = false
    }
  }, [id, language, key])

  return { doc: state?.key === key ? state.doc : null, loading: !!id && state?.key !== key }
}
