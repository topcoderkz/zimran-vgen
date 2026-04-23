import { useState } from 'react'
import { getSignedUploadUrl, uploadFileToGcs, registerVideo } from '../api/client'

interface UploadState {
  uploading: boolean
  progress: number
  error: string | null
}

export function useUpload(campaignId: string) {
  const [state, setState] = useState<UploadState>({
    uploading: false,
    progress: 0,
    error: null,
  })

  async function uploadFile(file: File, type: 'intro' | 'main') {
    setState({ uploading: true, progress: 0, error: null })

    try {
      // 1. Get signed URL
      const { upload_url, video_id } = await getSignedUploadUrl(campaignId, type, file.name)
      setState(s => ({ ...s, progress: 20 }))

      // 2. Upload to GCS
      const uploadRes = await uploadFileToGcs(upload_url, file)
      if (!uploadRes.ok) throw new Error(`Upload failed: ${uploadRes.status}`)
      setState(s => ({ ...s, progress: 80 }))

      // 3. Register with backend (extracts metadata via ffprobe)
      const video = await registerVideo(campaignId, video_id)
      setState({ uploading: false, progress: 100, error: null })

      return video
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setState({ uploading: false, progress: 0, error: msg })
      throw err
    }
  }

  return { ...state, uploadFile }
}
