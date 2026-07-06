export interface CvEducation {
  degree: string
  institution: string
  start_date?: string
  end_date?: string
  score?: string
}

export interface CvCertification {
  title: string
  issuer?: string
  date?: string
}

export interface CvProject {
  title: string
  description: string
  technologies?: string[]
  role?: string
  duration?: string
}

export interface CvSkills {
  technical?: string[]
  domain_specific?: string[]
  soft?: string[]
}

export interface CvStructured {
  name?: string
  domain?: string
  role_title?: string
  employment_type?: string
  total_experience_years?: number
  seniority?: string
  summary?: string
  education?: CvEducation[]
  certifications?: CvCertification[]
  skills?: CvSkills
  experience?: unknown[]
  projects?: CvProject[]
  trainings?: unknown[]
  raw_text?: string
}

export interface JdStructured {
  job_title?: string
  location?: string
  experience_range?: string
  minimum_qualification?: string
  skills_required?: string[]
  jd_summary?: string
}

export function asCvStructured(value: unknown): CvStructured | null {
  if (!value || typeof value !== 'object') return null
  return value as CvStructured
}

export function asJdStructured(value: unknown): JdStructured | null {
  if (!value || typeof value !== 'object') return null
  return value as JdStructured
}

export function formatTokenLabel(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}
