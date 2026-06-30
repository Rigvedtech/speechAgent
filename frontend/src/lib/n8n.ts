import { requestFormData } from '@/lib/api-client'
import type { JoinFormValues } from '@/schemas/join-form.schema'

export interface ExtractionApiResponse {
  success: boolean
  jdText?: string
  cvText?: string
  candidate_name?: string
  questions?: JoinFormValues['questions']
}

export interface N8nExtractionResult {
  jdText?: string
  cvText?: string
  candidateName?: string
  questions?: JoinFormValues['questions']
}

export async function extractJdCvFromFiles(
  jdFile: File | null,
  cvFile: File | null,
): Promise<N8nExtractionResult> {
  if (!jdFile && !cvFile) {
    throw new Error('Upload at least one document (JD or CV)')
  }

  const formData = new FormData()
  if (jdFile) formData.append('jd_file', jdFile)
  if (cvFile) formData.append('cv_file', cvFile)

  const data = await requestFormData<ExtractionApiResponse>('/api/extract-jd-cv', formData)

  return {
    jdText: data.jdText,
    cvText: data.cvText,
    candidateName: data.candidate_name,
    questions: data.questions,
  }
}
