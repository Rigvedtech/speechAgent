import {
  ArrowRight,
  BarChart3,
  ChevronDown,
  MessageCircleQuestion,
  Mic,
  Sparkles,
  Target,
  Video,
} from 'lucide-react'
import { AnimatedWaveform } from '@/components/landing/AnimatedWaveform'
import { FeatureCard } from '@/components/landing/FeatureCard'
import { PLATFORMS, PlatformBadge } from '@/components/landing/PlatformBadge'
import { Reveal } from '@/components/landing/Reveal'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { GetStartedLink } from '@/lib/marketing'

const STEPS = [
  {
    step: '01',
    title: 'Upload JD & resume',
    body: 'Add the role, job description, and candidate resume. Prabhat generates a tailored question plan for you to review.',
  },
  {
    step: '02',
    title: 'Paste your meeting room URI',
    body: 'Use the join link from your scheduler. Prabhat enters that room as a voice participant — no extra app for the candidate.',
  },
  {
    step: '03',
    title: 'Live AI interview',
    body: 'Natural voice Q&A in English or Hinglish, with follow-ups when answers stay shallow or drift.',
  },
  {
    step: '04',
    title: 'Report & feedback',
    body: 'Scored report for recruiters plus optional candidate feedback after the session.',
  },
] as const

const FAQ_ITEMS = [
  {
    q: 'How does Prabhat join my interview?',
    a: 'Paste the meeting room URI when you schedule the session. Prabhat joins that same call as a voice participant — no separate app for the candidate.',
  },
  {
    q: 'Which meeting platforms work today?',
    a: 'Major video platforms including Microsoft Teams, Zoom, Google Meet, and Webex. Use the direct join link from your meeting (for Teams, prefer the meet link — not the launcher wrapper URL).',
  },
  {
    q: 'Is it a fixed script or a real conversation?',
    a: 'You upload the JD and resume — Prabhat generates a question plan from them, and you review or edit it before the interview. During the call, Prabhat asks those questions in spoken language, greets from context, and can rephrase or follow up — but stays within the plan you approved.',
  },
  {
    q: 'What happens if the candidate goes off-topic?',
    a: 'Prabhat detects drift, refocuses or simplifies the question, asks a short probe when the tangent is still relevant, or moves on when the answer is not useful.',
  },
  {
    q: 'Can Prabhat ask follow-ups while the candidate is answering?',
    a: 'Yes. If an answer is shallow or mentions tools without explanation, Prabhat can ask a brief depth question — like an experienced recruiter. The flow is mostly turn-based: Prabhat speaks, then listens.',
  },
  {
    q: 'What languages are supported?',
    a: 'English and Hinglish for live voice interviews.',
  },
] as const

function FaqItem({ q, a }: { q: string; a: string }) {
  return (
    <Collapsible className="group border-b border-border last:border-b-0">
      <CollapsibleTrigger className="flex w-full cursor-pointer items-center justify-between gap-4 py-4 text-left text-sm font-medium transition-colors hover:text-foreground/90">
        <span>{q}</span>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-300 group-data-[state=open]:rotate-180"
          strokeWidth={1.5}
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="faq-content overflow-hidden text-sm text-muted-foreground">
        <p className="pb-4 leading-relaxed">{a}</p>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function LandingPage() {
  return (
    <div className="relative select-none">
      {/* Subtle hero atmosphere */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(124,58,237,0.08),transparent)] dark:bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(167,139,250,0.12),transparent)]"
        aria-hidden
      />

      {/* Hero */}
      <section className="relative mx-auto max-w-7xl px-4 pb-16 pt-12 sm:px-6 sm:pb-20 sm:pt-16 lg:px-8 lg:pb-24 lg:pt-20">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          <div>
            <Reveal>
              <Badge
                variant="outline"
                className="mb-5 border-border/80 bg-card/60 px-2.5 py-0.5 text-xs font-normal text-muted-foreground backdrop-blur-sm"
              >
                AI voice interviews for hiring teams
              </Badge>
            </Reveal>

            <Reveal delay={80}>
              <h1 className="max-w-xl text-3xl font-semibold tracking-tight sm:text-4xl lg:text-[2.75rem] lg:leading-[1.12]">
                Run AI voice interviews in{' '}
                <span className="text-[#7c3aed] dark:text-[#a78bfa]">any meeting room</span>
                {' '}— just paste the link.
              </h1>
            </Reveal>

            <Reveal delay={160}>
              <p className="mt-5 max-w-lg text-base leading-relaxed text-muted-foreground">
                Paste your meeting room URI — Prabhat joins the live call, conducts the interview
                plan you&apos;ve reviewed, and follows up with precision when answers drift or lack
                depth.
              </p>
            </Reveal>

            <Reveal delay={240}>
              <div className="mt-8">
                <Button asChild size="lg" className="group h-10 px-5">
                  <GetStartedLink>
                    Get started
                    <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
                  </GetStartedLink>
                </Button>
              </div>
            </Reveal>

            <Reveal delay={320} className="mt-10">
              <p className="mb-2.5 text-xs text-muted-foreground">Supported platforms</p>
              <div className="flex flex-wrap gap-2.5">
                {PLATFORMS.map((platform) => (
                  <PlatformBadge key={platform.id} platform={platform} />
                ))}
              </div>
            </Reveal>
          </div>

          <Reveal delay={120} className="relative mx-auto w-full max-w-md lg:max-w-none">
            <div className="landing-hero-panel relative cursor-pointer overflow-hidden rounded-xl border border-border bg-card p-6 shadow-[0_24px_80px_-40px_rgba(0,0,0,0.35)] sm:p-8 dark:shadow-[0_24px_80px_-40px_rgba(0,0,0,0.9)]">
              <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(124,58,237,0.04)_0%,transparent_50%)] dark:bg-[linear-gradient(135deg,rgba(167,139,250,0.06)_0%,transparent_50%)]" />
              <div className="relative flex flex-col items-center gap-6 py-4">
                <div className="relative flex h-24 w-24 items-center justify-center rounded-full border border-border bg-[#f5f5f5] dark:bg-muted">
                  <span className="absolute inset-0 rounded-full border border-foreground/10 landing-ring-pulse" />
                  <AnimatedWaveform className="scale-150" barClassName="bg-foreground" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">Prabhat</p>
                  <p className="mt-1 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                    <span className="live-dot" />
                    Listening in your meeting
                  </p>
                </div>
                <div className="w-full space-y-3 rounded-lg border border-border/80 bg-muted/30 p-4">
                  <div className="flex gap-2">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      &ldquo;You mentioned leading that project — can you walk me through your role
                      in more detail?&rdquo;
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#7c3aed]" />
                    <p className="text-xs leading-relaxed text-foreground/90">
                      Follow-up question · mid-answer
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-border/80 bg-muted/20 py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal className="mx-auto max-w-2xl text-center">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Built for real interviews, not scripts
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground sm:text-base">
              Paste a meeting room URI — Prabhat joins and runs the interview with recruiter-like
              judgment when the conversation gets messy.
            </p>
          </Reveal>

          <div className="mt-12 grid auto-rows-fr gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Reveal delay={0} className="h-full [&>*]:h-full">
              <FeatureCard
                accent="blue"
                icon={Mic}
                title="Meeting room URI, one setup"
                description="Paste the join link from your scheduler. Prabhat enters that room as a voice participant — candidates stay in the meeting they already use."
              />
            </Reveal>
            <Reveal delay={80} className="h-full [&>*]:h-full">
              <FeatureCard
                accent="violet"
                icon={Sparkles}
                title="Experienced recruiter tone"
                description="Calm, professional voice interviews from JD and resume context. One question at a time, rephrases when confused, no lecturing."
              />
            </Reveal>
            <Reveal delay={160} className="h-full [&>*]:h-full">
              <FeatureCard
                accent="amber"
                icon={Target}
                title="Depth when they drag"
                description="Detects shallow or off-topic answers. Refocuses the question or asks a short probe — then moves on when needed."
              />
            </Reveal>
            <Reveal delay={0} className="h-full [&>*]:h-full">
              <FeatureCard
                accent="emerald"
                icon={MessageCircleQuestion}
                title="AI-generated question bank"
                description="Questions are generated from the JD and resume you upload. Review and edit the plan before the interview — then Prabhat delivers it consistently in English or Hinglish."
              />
            </Reveal>
            <Reveal delay={80} className="h-full [&>*]:h-full">
              <FeatureCard
                accent="sky"
                icon={BarChart3}
                title="Scored reports"
                description="Per-question scores, strengths, gaps, and full transcript — ready for hiring managers on your dashboard."
              />
            </Reveal>
            <Reveal delay={160} className="h-full [&>*]:h-full">
              <FeatureCard
                accent="cyan"
                icon={Video}
                title="Live session visibility"
                description="Track bot status, active meetings, and session progress from the recruiter dashboard while the interview runs."
              />
            </Reveal>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal className="max-w-2xl">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">How it works</h2>
            <p className="mt-3 text-sm text-muted-foreground sm:text-base">
              From scheduling to report in four steps.
            </p>
          </Reveal>

          <ol className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map(({ step, title, body }, index) => (
              <Reveal key={step} delay={index * 70} className="list-none">
                <div className="landing-step-card h-full cursor-pointer rounded-xl border border-border bg-card p-5 transition-[border-color,background-color] duration-200 hover:border-foreground/15 hover:bg-muted/25 dark:hover:bg-muted/35">
                  <span className="text-xs font-medium tabular-nums text-[#7c3aed] dark:text-[#a78bfa]">
                    {step}
                  </span>
                  <h3 className="mt-3 text-sm font-semibold">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="border-t border-border/80 bg-muted/20 py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-10 lg:grid-cols-[1fr_1.2fr] lg:gap-16">
            <Reveal>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                Frequently asked questions
              </h2>
              <p className="mt-3 text-sm text-muted-foreground sm:text-base">
                Quick answers before you run your first AI screen.
              </p>
            </Reveal>

            <Reveal delay={100}>
              <div className="cursor-pointer rounded-xl border border-border bg-card px-5 sm:px-6">
                {FAQ_ITEMS.map((item) => (
                  <FaqItem key={item.q} q={item.q} a={item.a} />
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div
              className={cn(
                'relative cursor-pointer overflow-hidden rounded-2xl border border-border px-6 py-12 text-center sm:px-10 sm:py-14',
                'bg-card',
              )}
            >
              <div
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,rgba(124,58,237,0.1),transparent_55%)] dark:bg-[radial-gradient(circle_at_50%_120%,rgba(167,139,250,0.12),transparent_55%)]"
                aria-hidden
              />
              <div className="relative">
                <AnimatedWaveform className="mx-auto mb-6 justify-center opacity-60" />
                <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                  First rounds shouldn&apos;t slow your hiring.
                </h2>
                <p className="mx-auto mt-3 max-w-lg text-sm text-muted-foreground sm:text-base">
                  Share your meeting room link — Prabhat runs the interview plan you reviewed and
                  delivers a scored report your team can act on.
                </p>
                <div className="mt-8">
                  <Button asChild size="lg" className="group h-10">
                    <GetStartedLink>
                      Get started
                      <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
                    </GetStartedLink>
                  </Button>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-border/80 py-8">
        <div className="mx-auto max-w-7xl px-4 text-center text-xs text-muted-foreground sm:px-6 lg:px-8">
          <p>© {new Date().getFullYear()} Prabhat. AI voice interviews for hiring teams.</p>
        </div>
      </footer>
    </div>
  )
}
