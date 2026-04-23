import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getCampaign, startCampaign, listResults, listVideos, retryCombination } from '../api/client'
import { useUpload } from '../hooks/useUpload'
import type { Campaign, CombinationResult, Video } from '../types'

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [intros, setIntros] = useState<Video[]>([])
  const [mains, setMains] = useState<Video[]>([])
  const [results, setResults] = useState<CombinationResult[]>([])
  const [starting, setStarting] = useState(false)
  const [retrying, setRetrying] = useState<string | null>(null)
  const introUpload = useUpload(id!)
  const mainUpload = useUpload(id!)
  const introRef = useRef<HTMLInputElement>(null)
  const mainRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(() => {
    if (!id) return
    getCampaign(id).then(setCampaign)
    listVideos(id, 'intro').then(setIntros).catch(() => {})
    listVideos(id, 'main').then(setMains).catch(() => {})
    listResults(id).then(setResults).catch(() => {})
  }, [id])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 3000)
    return () => clearInterval(interval)
  }, [refresh])

  async function handleFiles(files: FileList | null, type: 'intro' | 'main') {
    if (!files) return
    const upload = type === 'intro' ? introUpload : mainUpload
    for (const file of Array.from(files)) {
      await upload.uploadFile(file, type)
    }
    refresh()
  }

  async function handleStart() {
    if (!id) return
    setStarting(true)
    try {
      await startCampaign(id)
      refresh()
    } finally {
      setStarting(false)
    }
  }

  async function handleRetry(combinationId: string) {
    if (!id) return
    setRetrying(combinationId)
    try {
      await retryCombination(id, combinationId)
      refresh()
    } finally {
      setRetrying(null)
    }
  }

  if (!campaign) return <p className="p-6 text-gray-500">Loading...</p>

  const progress = campaign.total_combinations > 0
    ? ((campaign.completed_count + campaign.failed_count) / campaign.total_combinations) * 100
    : 0

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{campaign.name}</h1>
          <p className="text-sm text-gray-500 mt-1">
            Status: {campaign.status} | {campaign.completed_count}/{campaign.total_combinations} done
            {campaign.failed_count > 0 && ` | ${campaign.failed_count} failed`}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      {campaign.status === 'processing' && (
        <div className="mb-6 w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-blue-600 h-3 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Upload section -- only in draft */}
      {campaign.status === 'draft' && (
        <div className="grid grid-cols-2 gap-6 mb-6">
          {/* Intros */}
          <div className="p-4 border border-dashed border-gray-300 rounded-lg">
            <h3 className="font-medium text-gray-700 mb-2">
              Intro Videos ({intros.length})
            </h3>
            {intros.length > 0 && (
              <ul className="mb-3 space-y-1">
                {intros.map(v => (
                  <li key={v.id} className="flex items-center justify-between text-sm text-gray-600 bg-gray-50 px-2 py-1 rounded">
                    <span className="truncate">{v.filename}</span>
                    {v.duration_seconds != null && (
                      <span className="text-xs text-gray-400 ml-2 shrink-0">{v.duration_seconds.toFixed(1)}s</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <input
              ref={introRef}
              type="file"
              accept="video/*"
              multiple
              className="hidden"
              onChange={e => handleFiles(e.target.files, 'intro')}
            />
            <button
              onClick={() => introRef.current?.click()}
              disabled={introUpload.uploading}
              className="w-full py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
            >
              {introUpload.uploading ? `Uploading... ${introUpload.progress}%` : '+ Add intros'}
            </button>
            {introUpload.error && <p className="text-red-500 text-xs mt-1">{introUpload.error}</p>}
          </div>

          {/* Mains */}
          <div className="p-4 border border-dashed border-gray-300 rounded-lg">
            <h3 className="font-medium text-gray-700 mb-2">
              Main Videos ({mains.length})
            </h3>
            {mains.length > 0 && (
              <ul className="mb-3 space-y-1">
                {mains.map(v => (
                  <li key={v.id} className="flex items-center justify-between text-sm text-gray-600 bg-gray-50 px-2 py-1 rounded">
                    <span className="truncate">{v.filename}</span>
                    {v.duration_seconds != null && (
                      <span className="text-xs text-gray-400 ml-2 shrink-0">{v.duration_seconds.toFixed(1)}s</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <input
              ref={mainRef}
              type="file"
              accept="video/*"
              multiple
              className="hidden"
              onChange={e => handleFiles(e.target.files, 'main')}
            />
            <button
              onClick={() => mainRef.current?.click()}
              disabled={mainUpload.uploading}
              className="w-full py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
            >
              {mainUpload.uploading ? `Uploading... ${mainUpload.progress}%` : '+ Add mains'}
            </button>
            {mainUpload.error && <p className="text-red-500 text-xs mt-1">{mainUpload.error}</p>}
          </div>
        </div>
      )}

      {/* Combination preview */}
      {campaign.status === 'draft' && intros.length > 0 && mains.length > 0 && (
        <p className="text-sm text-gray-500 mb-3">
          {intros.length} intro{intros.length > 1 ? 's' : ''} x {mains.length} main{mains.length > 1 ? 's' : ''} = <strong>{intros.length * mains.length} combinations</strong>
        </p>
      )}

      {/* Start button */}
      {campaign.status === 'draft' && (
        <button
          onClick={handleStart}
          disabled={starting || intros.length === 0 || mains.length === 0}
          className="w-full py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium mb-6"
        >
          {starting ? 'Starting...' : `Start Processing${intros.length > 0 && mains.length > 0 ? ` (${intros.length * mains.length} videos)` : ''}`}
        </button>
      )}

      {/* Results grid */}
      {results.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-gray-900 mb-3">Results</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2">Intro</th>
                  <th className="pb-2">Main</th>
                  <th className="pb-2">Status</th>
                  <th className="pb-2">Size</th>
                  <th className="pb-2">Duration</th>
                  <th className="pb-2"></th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <tr key={r.id} className="border-b border-gray-100">
                    <td className="py-2 text-gray-700">{r.intro_name}</td>
                    <td className="py-2 text-gray-700">{r.main_name}</td>
                    <td className="py-2">
                      <span className={`text-xs font-medium ${
                        r.status === 'completed' ? 'text-green-600' :
                        r.status === 'failed' ? 'text-red-600' :
                        r.status === 'processing' ? 'text-blue-600' : 'text-gray-400'
                      }`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="py-2 text-gray-500">
                      {r.output_size_bytes ? `${(r.output_size_bytes / 1048576).toFixed(1)} MB` : '-'}
                    </td>
                    <td className="py-2 text-gray-500">
                      {r.duration_seconds ? `${r.duration_seconds.toFixed(1)}s` : '-'}
                    </td>
                    <td className="py-2 space-x-2">
                      {r.download_url && (
                        <a
                          href={r.download_url}
                          className="text-blue-600 hover:underline"
                          download
                        >
                          Download
                        </a>
                      )}
                      {r.status === 'failed' && (
                        <button
                          onClick={() => handleRetry(r.id)}
                          disabled={retrying === r.id}
                          className="text-orange-600 hover:underline disabled:opacity-50"
                        >
                          {retrying === r.id ? 'Retrying...' : 'Retry'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
