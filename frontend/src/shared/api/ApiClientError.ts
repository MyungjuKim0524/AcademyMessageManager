import axios from 'axios'
import type { ApiErrorResponse, FieldErrorResponse } from './types'

export class ApiClientError extends Error {
  readonly code: string
  readonly fields: FieldErrorResponse[]

  constructor(
    message: string,
    code = 'CLIENT_ERROR',
    fields: FieldErrorResponse[] = [],
  ) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.fields = fields
  }
}

export function toApiClientError(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) return error

  if (axios.isAxiosError<ApiErrorResponse>(error)) {
    if (!error.response) {
      return new ApiClientError('백엔드 API에 연결할 수 없습니다. 서버 실행 상태를 확인해주세요.', 'NETWORK_ERROR')
    }

    const response = error.response.data
    return new ApiClientError(
      response?.message || '요청을 처리하지 못했습니다.',
      response?.code || `HTTP_${error.response.status}`,
      response?.fields || [],
    )
  }

  return new ApiClientError('예상하지 못한 오류가 발생했습니다.')
}
