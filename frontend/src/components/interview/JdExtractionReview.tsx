import { Building2, MapPin, Clock, GraduationCap } from 'lucide-react'
import type { JdStructured } from '@/types/extraction'
import { ExtractionSection } from '@/components/interview/ExtractionSection'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'

interface JdExtractionReviewProps {
  structured: JdStructured
  jdText: string
  onJdTextChange: (value: string) => void
}

export function JdExtractionReview({ structured, jdText, onJdTextChange }: JdExtractionReviewProps) {
  const skills = structured.skills_required ?? []

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-gradient-to-br from-muted/40 to-background p-4">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border bg-background">
            <Building2 className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
          </span>
          <div className="min-w-0 flex-1 space-y-3">
            <div>
              <h4 className="text-base font-semibold tracking-tight">
                {structured.job_title || 'Job description'}
              </h4>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {structured.experience_range ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5 shrink-0" />
                  <span>{structured.experience_range}</span>
                </div>
              ) : null}
              {structured.location ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  <span>{structured.location}</span>
                </div>
              ) : null}
              {structured.minimum_qualification ? (
                <div className="flex items-start gap-2 text-xs text-muted-foreground sm:col-span-2">
                  <GraduationCap className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span className="leading-relaxed">{structured.minimum_qualification}</span>
                </div>
              ) : null}
            </div>
            {structured.jd_summary ? (
              <p className="text-sm leading-relaxed text-foreground/90">{structured.jd_summary}</p>
            ) : null}
          </div>
        </div>
      </div>

      {skills.length > 0 && (
        <div className="max-h-[min(32vh,280px)] overflow-y-auto overflow-x-hidden pr-0.5">
          <ExtractionSection title="Required skills" count={skills.length} defaultOpen>
            <div className="flex flex-wrap gap-1.5">
              {skills.map((skill) => (
                <Badge key={skill} variant="outline" className="max-w-full">
                  <span className="truncate">{skill}</span>
                </Badge>
              ))}
            </div>
          </ExtractionSection>
        </div>
      )}

      <Separator />

      <div className="space-y-2">
        <div>
          <Label htmlFor="jdText">Job description text for interview</Label>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Edit the full extracted text used for question generation and the bot context.
          </p>
        </div>
        <Textarea
          id="jdText"
          value={jdText}
          onChange={(e) => onJdTextChange(e.target.value)}
          className="min-h-[140px] max-h-[220px] resize-y select-text text-sm leading-relaxed"
        />
        {jdText.trim().length > 0 && jdText.trim().length < 100 && (
          <p className="text-xs text-muted-foreground">
            At least 100 characters required ({jdText.trim().length}/100)
          </p>
        )}
      </div>
    </div>
  )
}
