export interface QualitySettings {
  codec: 'copy' | 'h264' | 'h265'
  resolution: string
  crf?: number
  audio_bitrate: string
}

export interface Campaign {
  id: string
  user_id: string
  name: string
  status: 'draft' | 'processing' | 'completed' | 'failed'
  quality: QualitySettings
  total_combinations: number
  completed_count: number
  failed_count: number
  created_at: string
  completed_at: string | null
}

export interface Video {
  id: string
  campaign_id: string
  type: 'intro' | 'main'
  filename: string
  gcs_path: string
  size_bytes: number | null
  duration_seconds: number | null
  codec: string | null
  width: number | null
  height: number | null
  uploaded_at: string
}

export interface CombinationResult {
  id: string
  intro_name: string
  main_name: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  output_size_bytes: number | null
  duration_seconds: number | null
  download_url: string | null
}

export interface SignedUrlResponse {
  upload_url: string
  video_id: string
  gcs_path: string
}
