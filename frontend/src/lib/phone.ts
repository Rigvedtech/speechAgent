/** Keep in sync with backend/services/phone.py */

export interface PhoneCountry {
  iso: string
  name: string
  dial: string
  min: number
  max: number
}

export const PHONE_COUNTRIES: PhoneCountry[] = [
  { iso: 'IN', name: 'India', dial: '91', min: 10, max: 10 },
  { iso: 'US', name: 'United States', dial: '1', min: 10, max: 10 },
  { iso: 'GB', name: 'United Kingdom', dial: '44', min: 10, max: 10 },
  { iso: 'AE', name: 'United Arab Emirates', dial: '971', min: 9, max: 9 },
  { iso: 'SG', name: 'Singapore', dial: '65', min: 8, max: 8 },
  { iso: 'AU', name: 'Australia', dial: '61', min: 9, max: 9 },
  { iso: 'DE', name: 'Germany', dial: '49', min: 10, max: 11 },
  { iso: 'FR', name: 'France', dial: '33', min: 9, max: 9 },
  { iso: 'SA', name: 'Saudi Arabia', dial: '966', min: 9, max: 9 },
  { iso: 'PK', name: 'Pakistan', dial: '92', min: 10, max: 10 },
  { iso: 'BD', name: 'Bangladesh', dial: '880', min: 10, max: 10 },
  { iso: 'NP', name: 'Nepal', dial: '977', min: 10, max: 10 },
  { iso: 'LK', name: 'Sri Lanka', dial: '94', min: 9, max: 9 },
  { iso: 'MY', name: 'Malaysia', dial: '60', min: 9, max: 10 },
  { iso: 'PH', name: 'Philippines', dial: '63', min: 10, max: 10 },
  { iso: 'ID', name: 'Indonesia', dial: '62', min: 9, max: 11 },
  { iso: 'NL', name: 'Netherlands', dial: '31', min: 9, max: 9 },
  { iso: 'ZA', name: 'South Africa', dial: '27', min: 9, max: 9 },
  { iso: 'CA', name: 'Canada', dial: '1', min: 10, max: 10 },
]

export const DEFAULT_PHONE_ISO = 'IN'

export function phoneCountry(iso: string): PhoneCountry {
  return PHONE_COUNTRIES.find((row) => row.iso === iso) ?? PHONE_COUNTRIES[0]
}

export function nationalDigits(value: string): string {
  return value.replace(/\D/g, '')
}

export function validateNationalNumber(iso: string, raw: string): { ok: true; e164: string } | { ok: false; message: string } {
  const country = phoneCountry(iso)
  let national = nationalDigits(raw)
  if (national.startsWith('0')) national = national.replace(/^0+/, '')
  if (!national) {
    return { ok: false, message: 'Enter your phone number.' }
  }
  if (national.length < country.min || national.length > country.max) {
    if (country.min === country.max) {
      return { ok: false, message: `${country.name} numbers must be ${country.min} digits.` }
    }
    return {
      ok: false,
      message: `${country.name} numbers must be ${country.min}–${country.max} digits.`,
    }
  }
  return { ok: true, e164: `+${country.dial}${national}` }
}

const PHONE_EXAMPLES: Record<string, string> = {
  IN: '98765 43210',
  US: '202 555 0100',
  GB: '7400 123456',
  AE: '50 123 4567',
  SG: '8123 4567',
  AU: '412 345 678',
  DE: '151 2345678',
  FR: '6 12 34 56 78',
  SA: '51 234 5678',
  PK: '300 1234567',
  BD: '1712 345678',
  NP: '9841 234567',
  LK: '71 234 5678',
  MY: '12 345 6789',
  PH: '917 123 4567',
  ID: '812 3456 789',
  NL: '6 12345678',
  ZA: '82 123 4567',
  CA: '416 555 0100',
}

export function phonePlaceholder(iso: string): string {
  return PHONE_EXAMPLES[iso] ?? 'Your number'
}

export function countryFlagSrc(iso: string): string {
  return `https://flagcdn.com/w40/${iso.toLowerCase()}.png`
}
