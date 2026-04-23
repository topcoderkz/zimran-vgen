import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCampaign } from '../api/client'
import type { QualitySettings } from '../types'

export default function CampaignBuilder() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [quality, setQuality] = useState<QualitySettings>({
    codec: 'copy',
    resolution: 'original',
    audio_bitrate: 'original',
  })
  const [submitting, setSubmitting] = useState(false)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSubmitting(true)
    try {
      const campaign = await createCampaign(name.trim(), quality)
      navigate(`/campaigns/${campaign.id}`)
    } catch (err) {
      console.error(err)
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">New Campaign</h1>

      <form onSubmit={handleCreate} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Campaign Name
          </label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Q2 Product Launch"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Video Codec
          </label>
          <select
            value={quality.codec}
            onChange={e => setQuality(q => ({ ...q, codec: e.target.value as QualitySettings['codec'] }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          >
            <option value="copy">Lossless (stream copy) - fastest</option>
            <option value="h264">H.264 (re-encode)</option>
            <option value="h265">H.265 (re-encode, smaller files)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Resolution
          </label>
          <select
            value={quality.resolution}
            onChange={e => setQuality(q => ({ ...q, resolution: e.target.value }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          >
            <option value="original">Original</option>
            <option value="1920x1080">1080p</option>
            <option value="1280x720">720p</option>
          </select>
        </div>

        {quality.codec !== 'copy' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Quality (CRF): {quality.crf ?? 23}
            </label>
            <input
              type="range"
              min={18}
              max={28}
              value={quality.crf ?? 23}
              onChange={e => setQuality(q => ({ ...q, crf: Number(e.target.value) }))}
              className="w-full"
            />
            <p className="text-xs text-gray-500 mt-1">Lower = higher quality, larger files</p>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !name.trim()}
          className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {submitting ? 'Creating...' : 'Create Campaign'}
        </button>
      </form>
    </div>
  )
}
