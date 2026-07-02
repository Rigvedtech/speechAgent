import { request, requestFormData } from '@/lib/api-client'
import type { JoinFormValues } from '@/schemas/join-form.schema'

export interface CvExtractionApiResponse {
  success: boolean
  cvText?: string
  cvStructured?: Record<string, unknown>
  candidate_name?: string
}

export interface JdExtractionApiResponse {
  success: boolean
  jdText?: string
  jdStructured?: Record<string, unknown>
}

export interface QuestionsApiResponse {
  success: boolean
  questions?: JoinFormValues['questions']
}

export interface CvExtractionResult {
  cvText?: string
  cvStructured?: Record<string, unknown>
  candidateName?: string
}

export interface JdExtractionResult {
  jdText?: string
  jdStructured?: Record<string, unknown>
}

export interface QuestionsGenerationResult {
  questions?: JoinFormValues['questions']
}

export async function extractCvFromFile(cvFile: File): Promise<CvExtractionResult> {
  const formData = new FormData()
  formData.append('cv_file', cvFile)

  const data = await requestFormData<CvExtractionApiResponse>('/api/extract-cv', formData)

  return {
    cvText: data.cvText,
    cvStructured: data.cvStructured,
    candidateName: data.candidate_name,
  }
}

export async function extractJdFromFile(jdFile: File): Promise<JdExtractionResult> {
  const formData = new FormData()
  formData.append('jd_file', jdFile)

  const data = await requestFormData<JdExtractionApiResponse>('/api/extract-jd', formData)

  return {
    jdText: data.jdText,
    jdStructured: data.jdStructured,
  }
}

export async function generateQuestionsFromText(
  jdText: string,
  cvText: string,
  options: { candidateName?: string; languageMode?: string } = {},
): Promise<QuestionsGenerationResult> {
  const data = await request<QuestionsApiResponse>('/api/generate-questions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jdText,
      cvText,
      candidate_name: options.candidateName?.trim() || undefined,
      language_mode: options.languageMode,
    }),
    timeoutMs: 180000,
  })

  return { questions: data.questions }
}

export async function extractDocumentsFromFiles(
  jdFile: File | null,
  cvFile: File | null,
): Promise<CvExtractionResult & JdExtractionResult> {
  if (!jdFile && !cvFile) {
    throw new Error('Upload at least one document (JD or CV)')
  }

  const [cvResult, jdResult] = await Promise.all([
    cvFile ? extractCvFromFile(cvFile) : Promise.resolve({} as CvExtractionResult),
    jdFile ? extractJdFromFile(jdFile) : Promise.resolve({} as JdExtractionResult),
  ])

  return { ...cvResult, ...jdResult }
}
