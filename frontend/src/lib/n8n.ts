import { request, requestFormData } from '@/lib/api-client'
import type { JoinFormValues } from '@/schemas/join-form.schema'

export interface CvExtractionApiResponse {
  success: boolean
  cvText?: string
  cvStructured?: Record<string, unknown>
  candidate_name?: string
  extraction_id?: string
  document_id?: string
}

export interface JdExtractionApiResponse {
  success: boolean
  jdText?: string
  jdStructured?: Record<string, unknown>
  extraction_id?: string
  document_id?: string
}

export interface QuestionsApiResponse {
  success: boolean
  questions?: JoinFormValues['questions']
  extraction_id?: string
}

export interface CvExtractionResult {
  cvText?: string
  cvStructured?: Record<string, unknown>
  candidateName?: string
  extractionId?: string
  documentId?: string
}

export interface JdExtractionResult {
  jdText?: string
  jdStructured?: Record<string, unknown>
  extractionId?: string
  documentId?: string
}

export interface QuestionsGenerationResult {
  questions?: JoinFormValues['questions']
  extractionId?: string
}

export async function extractCvFromFile(
  cvFile: File,
  options: { candidateId?: string | null } = {},
): Promise<CvExtractionResult> {
  const formData = new FormData()
  formData.append('cv_file', cvFile)
  if (options.candidateId) {
    formData.append('candidate_id', options.candidateId)
  }

  const data = await requestFormData<CvExtractionApiResponse>('/api/extract-cv', formData)

  return {
    cvText: data.cvText,
    cvStructured: data.cvStructured,
    candidateName: data.candidate_name,
    extractionId: data.extraction_id,
    documentId: data.document_id,
  }
}

export async function extractJdFromFile(
  jdFile: File,
  options: { jobPostingId?: string | null } = {},
): Promise<JdExtractionResult> {
  const formData = new FormData()
  formData.append('jd_file', jdFile)
  if (options.jobPostingId) {
    formData.append('job_posting_id', options.jobPostingId)
  }

  const data = await requestFormData<JdExtractionApiResponse>('/api/extract-jd', formData)

  return {
    jdText: data.jdText,
    jdStructured: data.jdStructured,
    extractionId: data.extraction_id,
    documentId: data.document_id,
  }
}

export async function generateQuestionsFromText(
  jdText: string,
  cvText: string,
  options: {
    candidateName?: string
    languageMode?: string
    candidateId?: string | null
    jobPostingId?: string | null
    extractionId?: string | null
  } = {},
): Promise<QuestionsGenerationResult> {
  const data = await request<QuestionsApiResponse>('/api/generate-questions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jdText,
      cvText,
      candidate_name: options.candidateName?.trim() || undefined,
      language_mode: options.languageMode,
      candidate_id: options.candidateId || undefined,
      job_posting_id: options.jobPostingId || undefined,
      extraction_id: options.extractionId || undefined,
    }),
    timeoutMs: 180000,
  })

  return { questions: data.questions, extractionId: data.extraction_id }
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
