export type StaffRole = 'ADMIN' | 'TEACHER' | 'ASSISTANT'

export interface CurrentStaff {
  id: number
  email: string
  display_name?: string | null
  role: StaffRole
}

export interface AuthResponse {
  user: CurrentStaff
}
