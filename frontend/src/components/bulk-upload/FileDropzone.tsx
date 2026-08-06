import { FileCheck2, UploadCloud } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface FileDropzoneProps {
  id: string
  title: string
  hint: string
  disabled?: boolean
  multiple?: boolean
  selectedLabel?: string
  onFiles: (files: File[]) => void
}

export function FileDropzone({
  id,
  title,
  hint,
  disabled = false,
  multiple = false,
  selectedLabel,
  onFiles,
}: FileDropzoneProps) {
  return (
    <div
      className={cn(
        'relative rounded-lg border border-dashed p-6 text-center transition-colors',
        disabled
          ? 'border-border bg-muted/30 text-muted-foreground'
          : 'border-input bg-muted/20 hover:border-foreground/30 hover:bg-muted/45',
      )}
    >
      <Input
        id={id}
        type="file"
        multiple={multiple}
        disabled={disabled}
        accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
        className="sr-only"
        onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
      />
      <label
        htmlFor={id}
        className={cn('flex flex-col items-center', disabled ? 'cursor-not-allowed' : 'cursor-pointer')}
      >
        <span
          className={cn(
            'mb-3 flex h-10 w-10 items-center justify-center rounded-full',
            selectedLabel ? 'bg-success/10 text-success' : 'bg-muted text-foreground',
          )}
        >
          {selectedLabel ? <FileCheck2 className="h-5 w-5" /> : <UploadCloud className="h-5 w-5" />}
        </span>
        <span className="text-sm font-medium text-foreground">{selectedLabel ?? title}</span>
        <span className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{hint}</span>
      </label>
    </div>
  )
}
