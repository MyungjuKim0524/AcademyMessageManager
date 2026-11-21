import { apiClient } from '../../shared/api/client'
import { toApiClientError } from '../../shared/api/ApiClientError'
import type { HealthResponse, MessagePreviewRequest, MessagePreviewResponse } from './types'

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const { data } = await apiClient.get<HealthResponse>('/api/health')
    return data
  } catch (error) {
    throw toApiClientError(error)
  }
}

export async function createMessagePreview(request: MessagePreviewRequest): Promise<MessagePreviewResponse> {
  try {
    const { data } = await apiClient.post<MessagePreviewResponse>('/api/messages/preview', request)
    return data
  } catch (error) {
    throw toApiClientError(error)
  }
}
