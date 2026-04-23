import type { Campaign, CombinationResult, QualitySettings, SignedUrlResponse, Video } from '../types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// Campaigns
export const createCampaign = (name: string, quality: QualitySettings) =>
  request<Campaign>('/campaigns', {
    method: 'POST',
    body: JSON.stringify({ name, quality }),
  })

export const listCampaigns = () =>
  request<Campaign[]>('/campaigns')

export const getCampaign = (id: string) =>
  request<Campaign>(`/campaigns/${id}`)

export const deleteCampaign = (id: string) =>
  request<void>(`/campaigns/${id}`, { method: 'DELETE' })

export const startCampaign = (id: string) =>
  request<{ status: string; total_combinations: number }>(`/campaigns/${id}/start`, {
    method: 'POST',
  })

// Uploads
export const getSignedUploadUrl = (campaignId: string, type: 'intro' | 'main', filename: string) =>
  request<SignedUrlResponse>('/upload/signed-url', {
    method: 'POST',
    body: JSON.stringify({ campaign_id: campaignId, type, filename }),
  })

export const uploadFileToGcs = (url: string, file: File) =>
  fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'video/mp4' },
    body: file,
  })

export const registerVideo = (campaignId: string, videoId: string) =>
  request<Video>(`/campaigns/${campaignId}/videos`, {
    method: 'POST',
    body: JSON.stringify({ video_id: videoId }),
  })

// Results
export const listResults = (campaignId: string, status?: string) => {
  const params = status ? `?status=${status}` : ''
  return request<CombinationResult[]>(`/campaigns/${campaignId}/results${params}`)
}

export const getDownloadUrl = (combinationId: string) =>
  request<{ download_url: string }>(`/download/${combinationId}`)
