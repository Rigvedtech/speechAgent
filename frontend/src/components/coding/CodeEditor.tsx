import Editor from '@monaco-editor/react'
import { useTheme } from '@/hooks/useTheme'

type CodeEditorProps = {
  value: string
  onChange?: (value: string) => void
  language?: string
  height?: string
  readOnly?: boolean
}

function monacoLanguage(language: string): string {
  const lang = language.toLowerCase()
  if (lang === 'javascript' || lang === 'js') return 'javascript'
  if (lang === 'typescript' || lang === 'ts') return 'typescript'
  if (lang === 'java') return 'java'
  if (lang === 'cpp' || lang === 'c++') return 'cpp'
  if (lang === 'csharp' || lang === 'c#') return 'csharp'
  if (lang === 'go') return 'go'
  if (lang === 'ruby') return 'ruby'
  if (lang === 'php') return 'php'
  if (lang === 'kotlin') return 'kotlin'
  if (lang === 'rust') return 'rust'
  if (lang === 'swift') return 'swift'
  return 'python'
}

export function CodeEditor({
  value,
  onChange,
  language = 'python',
  height = '100%',
  readOnly = false,
}: CodeEditorProps) {
  const { theme } = useTheme()

  return (
    <Editor
      height={height}
      language={monacoLanguage(language)}
      value={value}
      onChange={(next) => onChange?.(next ?? '')}
      theme={theme === 'dark' ? 'vs-dark' : 'light'}
      options={{
        minimap: { enabled: false },
        fontSize: 14,
        wordWrap: 'on',
        automaticLayout: true,
        readOnly,
        scrollBeyondLastLine: false,
        tabSize: 2,
        renderLineHighlight: 'line',
        padding: { top: 12, bottom: 12 },
      }}
      loading={<div className="p-4 text-sm text-muted-foreground">Loading editor…</div>}
    />
  )
}
