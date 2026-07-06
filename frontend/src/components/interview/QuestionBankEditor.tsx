import { useFieldArray, useFormContext } from 'react-hook-form'
import { Plus, Trash2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { JoinFormValues } from '@/schemas/join-form.schema'

const defaultRow = {
  id: '1',
  difficulty: 'Low' as const,
  source: 'jd' as const,
  question: '',
}

interface QuestionBankEditorProps {
  fillHeight?: boolean
}

export function QuestionBankEditor({ fillHeight = false }: QuestionBankEditorProps) {
  const { control, register, setValue, watch } = useFormContext<JoinFormValues>()
  const { fields, append, remove } = useFieldArray({ control, name: 'questions' })
  const questions = watch('questions')

  const handleImport = () => {
    const raw = window.prompt('Paste JSON array of questions:')
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as JoinFormValues['questions']
      if (!Array.isArray(parsed)) throw new Error('Expected array')
      parsed.forEach((q, i) => {
        if (i < fields.length) {
          setValue(`questions.${i}`, q)
        } else {
          append(q)
        }
      })
    } catch {
      window.alert('Invalid JSON')
    }
  }

  return (
    <div className={cn('flex flex-col', fillHeight && 'min-h-0 flex-1')}>
      <div className="mb-3 flex shrink-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <Label>Question bank</Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
           The bot asks{' '}
            <span className="font-medium text-foreground">10 during the interview</span> — 4 Low,
            3 Hard, and 3 Intermediate — picked from this bank.
          </p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={handleImport}>
            <Upload className="h-4 w-4" />
            Import JSON
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => append({ ...defaultRow, id: String(fields.length + 1) })}
          >
            <Plus className="h-4 w-4" />
            Add row
          </Button>
        </div>
      </div>

      <div
        className={cn(
          'space-y-3 overflow-y-auto overflow-x-hidden pr-1',
          fillHeight ? 'min-h-0 flex-1' : 'max-h-[min(52vh,440px)]',
        )}
      >
        {fields.map((field, index) => (
          <div
            key={field.id}
            className="grid gap-3 rounded-lg border border-border p-4 md:grid-cols-[80px_120px_100px_1fr_40px]"
          >
            <div>
              <Label className="text-xs">ID</Label>
              <Input {...register(`questions.${index}.id`)} />
            </div>
            <div>
              <Label className="text-xs">Difficulty</Label>
              <Select
                value={questions?.[index]?.difficulty}
                onValueChange={(v) =>
                  setValue(`questions.${index}.difficulty`, v as JoinFormValues['questions'][number]['difficulty'])
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Low">Low</SelectItem>
                  <SelectItem value="Intermediate">Intermediate</SelectItem>
                  <SelectItem value="Hard">Hard</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Source</Label>
              <Select
                value={questions?.[index]?.source}
                onValueChange={(v) =>
                  setValue(`questions.${index}.source`, v as JoinFormValues['questions'][number]['source'])
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="jd">JD</SelectItem>
                  <SelectItem value="resume">Resume</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Question</Label>
              <Input {...register(`questions.${index}.question`)} />
            </div>
            <div className="flex items-end">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => remove(index)}
                disabled={fields.length <= 1}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
