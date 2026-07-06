import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useInView } from '@/hooks/useInView'

interface RevealProps {
  children: ReactNode
  className?: string
  delay?: number
}

export function Reveal({ children, className, delay = 0 }: RevealProps) {
  const { ref, inView } = useInView({ threshold: 0.08, rootMargin: '0px 0px -6% 0px' })

  return (
    <div
      ref={ref}
      className={cn('reveal', inView && 'reveal-visible', className)}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}
