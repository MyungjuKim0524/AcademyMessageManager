export interface FieldErrorResponse {
  field: string
  message: string
}

export interface ApiErrorResponse {
  code: string
  message: string
  fields: FieldErrorResponse[]
}
