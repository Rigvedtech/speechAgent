import type { CodingLanguage } from '@/types/api'

/** Languages available for domains / Monaco / AI generate. */
export const CODING_LANGUAGE_OPTIONS: {
  id: CodingLanguage
  label: string
  entry: string
  monaco: string
}[] = [
  { id: 'python', label: 'Python', entry: 'main.py', monaco: 'python' },
  { id: 'java', label: 'Java', entry: 'Solution.java', monaco: 'java' },
  { id: 'javascript', label: 'JavaScript', entry: 'main.js', monaco: 'javascript' },
  { id: 'typescript', label: 'TypeScript', entry: 'main.ts', monaco: 'typescript' },
  { id: 'cpp', label: 'C++', entry: 'main.cpp', monaco: 'cpp' },
  { id: 'csharp', label: 'C#', entry: 'Solution.cs', monaco: 'csharp' },
  { id: 'go', label: 'Go', entry: 'main.go', monaco: 'go' },
  { id: 'ruby', label: 'Ruby', entry: 'main.rb', monaco: 'ruby' },
  { id: 'php', label: 'PHP', entry: 'main.php', monaco: 'php' },
  { id: 'kotlin', label: 'Kotlin', entry: 'Solution.kt', monaco: 'kotlin' },
  { id: 'rust', label: 'Rust', entry: 'main.rs', monaco: 'rust' },
  { id: 'swift', label: 'Swift', entry: 'main.swift', monaco: 'swift' },
]

export function codingLanguageMeta(id: string) {
  return (
    CODING_LANGUAGE_OPTIONS.find((o) => o.id === id) ?? CODING_LANGUAGE_OPTIONS[0]
  )
}

export function defaultEntryForLanguage(language: string) {
  return codingLanguageMeta(language).entry
}

export function monacoLanguageFor(path: string, language: string) {
  if (path.endsWith('.ts') || path.endsWith('.tsx')) return 'typescript'
  if (path.endsWith('.js') || path.endsWith('.jsx')) return 'javascript'
  if (path.endsWith('.json')) return 'json'
  if (path.endsWith('.md')) return 'markdown'
  if (path.endsWith('.java')) return 'java'
  if (path.endsWith('.cpp') || path.endsWith('.cc') || path.endsWith('.h')) return 'cpp'
  if (path.endsWith('.cs')) return 'csharp'
  if (path.endsWith('.go')) return 'go'
  if (path.endsWith('.rb')) return 'ruby'
  if (path.endsWith('.php')) return 'php'
  if (path.endsWith('.kt')) return 'kotlin'
  if (path.endsWith('.rs')) return 'rust'
  if (path.endsWith('.swift')) return 'swift'
  if (path.endsWith('.py')) return 'python'
  return codingLanguageMeta(language).monaco
}
