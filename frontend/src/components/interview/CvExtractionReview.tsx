import { Briefcase, GraduationCap, User } from 'lucide-react'
import type { CvStructured } from '@/types/extraction'
import { formatTokenLabel } from '@/types/extraction'
import { ExtractionSection, SkillGroup } from '@/components/interview/ExtractionSection'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'

interface CvExtractionReviewProps {
  structured: CvStructured
  cvText: string
  onCvTextChange: (value: string) => void
}

export function CvExtractionReview({ structured, cvText, onCvTextChange }: CvExtractionReviewProps) {
  const technical = structured.skills?.technical ?? []
  const domainSkills = structured.skills?.domain_specific ?? []
  const softSkills = structured.skills?.soft ?? []
  const education = structured.education ?? []
  const projects = structured.projects ?? []
  const certifications = structured.certifications?.filter((c) => c.title?.trim()) ?? []

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-gradient-to-br from-muted/40 to-background p-4">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border bg-background">
            <User className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
          </span>
          <div className="min-w-0 flex-1 space-y-2">
            <div>
              <h4 className="truncate text-base font-semibold tracking-tight">
                {structured.name || 'Candidate profile'}
              </h4>
              {structured.role_title ? (
                <p className="mt-0.5 text-sm text-muted-foreground">{structured.role_title}</p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {structured.domain ? (
                <Badge variant="outline">{formatTokenLabel(structured.domain)}</Badge>
              ) : null}
              {structured.seniority ? (
                <Badge variant="secondary">{formatTokenLabel(structured.seniority)}</Badge>
              ) : null}
              {structured.employment_type ? (
                <Badge variant="secondary">{formatTokenLabel(structured.employment_type)}</Badge>
              ) : null}
              {structured.total_experience_years !== undefined ? (
                <Badge variant="outline">
                  {structured.total_experience_years}{' '}
                  {structured.total_experience_years === 1 ? 'year' : 'years'} exp.
                </Badge>
              ) : null}
            </div>
            {structured.summary ? (
              <p className="text-sm leading-relaxed text-foreground/90">{structured.summary}</p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="max-h-[min(42vh,380px)] space-y-3 overflow-y-auto overflow-x-hidden pr-0.5">
        {(technical.length > 0 || domainSkills.length > 0 || softSkills.length > 0) && (
          <ExtractionSection
            title="Skills"
            count={technical.length + domainSkills.length + softSkills.length}
            defaultOpen
          >
            <div className="space-y-3">
              <SkillGroup label="Technical" items={technical} />
              <SkillGroup label="Domain" items={domainSkills} />
              <SkillGroup label="Soft skills" items={softSkills} />
            </div>
          </ExtractionSection>
        )}

        {education.length > 0 && (
          <ExtractionSection title="Education" count={education.length}>
            <ul className="space-y-2.5">
              {education.map((item, index) => (
                <li
                  key={`${item.degree}-${index}`}
                  className="rounded-lg border border-border/80 bg-background p-3"
                >
                  <div className="flex items-start gap-2">
                    <GraduationCap className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{item.degree}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{item.institution}</p>
                      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                        {(item.start_date || item.end_date) && (
                          <span>
                            {item.start_date}
                            {item.start_date && item.end_date ? ' – ' : ''}
                            {item.end_date}
                          </span>
                        )}
                        {item.score ? <span>{item.score}</span> : null}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </ExtractionSection>
        )}

        {projects.length > 0 && (
          <ExtractionSection title="Projects" count={projects.length}>
            <ul className="space-y-2.5">
              {projects.map((project, index) => (
                <li
                  key={`${project.title}-${index}`}
                  className="rounded-lg border border-border/80 bg-background p-3"
                >
                  <div className="flex items-start gap-2">
                    <Briefcase className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <p className="text-sm font-medium">{project.title}</p>
                      <p className="text-xs leading-relaxed text-muted-foreground">
                        {project.description}
                      </p>
                      {project.technologies?.length ? (
                        <div className="flex flex-wrap gap-1">
                          {project.technologies.map((tech) => (
                            <span
                              key={`${project.title}-${tech}`}
                              className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                            >
                              {tech}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </ExtractionSection>
        )}

        {certifications.length > 0 && (
          <ExtractionSection title="Certifications" count={certifications.length}>
            <ul className="space-y-1.5 text-sm">
              {certifications.map((cert, index) => (
                <li key={`${cert.title}-${index}`} className="text-foreground/90">
                  {cert.title}
                  {cert.issuer ? (
                    <span className="text-muted-foreground"> · {cert.issuer}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </ExtractionSection>
        )}
      </div>

      <Separator />

      <div className="space-y-2">
        <div>
          <Label htmlFor="cvText">Resume text for interview</Label>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Edit the full extracted text used for question generation and the bot context.
          </p>
        </div>
        <Textarea
          id="cvText"
          value={cvText}
          onChange={(e) => onCvTextChange(e.target.value)}
          className="min-h-[140px] max-h-[220px] resize-y select-text font-mono text-xs leading-relaxed"
        />
        {cvText.trim().length > 0 && cvText.trim().length < 50 && (
          <p className="text-xs text-muted-foreground">
            At least 50 characters required ({cvText.trim().length}/50)
          </p>
        )}
      </div>
    </div>
  )
}
