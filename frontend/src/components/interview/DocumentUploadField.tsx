import { useRef } from 'react'
import { Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface DocumentUploadFieldProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  accept?: string
  file: File | null
  onFileSelect: (file: File | null) => void
  disabled?: boolean
  minHeight?: string
}

export function DocumentUploadField({
  id,
  label,
  value,
  onChange,
  error,
  accept = '.pdf,.doc,.docx,.txt',
  file,
  onFileSelect,
  disabled,
  minHeight = '160px',
}: DocumentUploadFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <div className="flex items-center gap-2">
          {file && (
            <span className="max-w-[220px] truncate text-xs text-muted-foreground">{file.name}</span>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              const selected = e.target.files?.[0] ?? null
              onFileSelect(selected)
              e.target.value = ''
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
          >
            <Upload className="h-4 w-4" />
            Upload
          </Button>
          {file && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onFileSelect(null)}
              disabled={disabled}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      <Textarea
        id={id}
        className="min-h-[160px]"
        style={{ minHeight }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  )
}
