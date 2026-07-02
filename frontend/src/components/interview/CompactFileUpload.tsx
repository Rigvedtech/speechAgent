import { useRef } from 'react'
import { FileText, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface CompactFileUploadProps {
  label: string
  hint?: string
  accept?: string
  file: File | null
  onFileSelect: (file: File | null) => void
  disabled?: boolean
  error?: string
}

export function CompactFileUpload({
  label,
  hint = 'PDF, DOC, DOCX, or TXT',
  accept = '.pdf,.doc,.docx,.txt',
  file,
  onFileSelect,
  disabled,
  error,
}: CompactFileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="select-none">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          onFileSelect(e.target.files?.[0] ?? null)
          e.target.value = ''
        }}
      />
      <div
        className={cn(
          'flex w-full items-center gap-3 rounded-xl border border-dashed border-border bg-muted/20 px-4 py-3 transition-colors',
          'hover:border-foreground/20 hover:bg-muted/40',
          disabled && 'pointer-events-none opacity-50',
          file && 'border-solid border-foreground/15 bg-card',
        )}
      >
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="flex min-w-0 flex-1 items-center gap-4 text-left"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-border bg-card">
            {file ? (
              <FileText className="h-5 w-5 text-foreground/70" strokeWidth={1.25} />
            ) : (
              <Upload className="h-5 w-5 text-muted-foreground" strokeWidth={1.25} />
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">{label}</span>
            {file ? (
              <span className="mt-0.5 block truncate text-xs text-muted-foreground">{file.name}</span>
            ) : (
              <span className="mt-0.5 block text-xs text-muted-foreground">{hint}</span>
            )}
          </span>
        </button>
        {file ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={disabled}
            onClick={() => onFileSelect(null)}
          >
            <X className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
      {error ? <p className="mt-1.5 text-xs text-destructive">{error}</p> : null}
    </div>
  )
}
