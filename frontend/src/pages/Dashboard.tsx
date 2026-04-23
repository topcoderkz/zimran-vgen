import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listCampaigns } from '../api/client'
import type { Campaign } from '../types'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  processing: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
}

export default function Dashboard() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listCampaigns()
      .then(setCampaigns)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
        <Link
          to="/campaigns/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          New Campaign
        </Link>
      </div>

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg">No campaigns yet</p>
          <p className="mt-1">Create your first campaign to get started</p>
        </div>
      ) : (
        <div className="space-y-3">
          {campaigns.map(c => (
            <Link
              key={c.id}
              to={`/campaigns/${c.id}`}
              className="block p-4 bg-white rounded-lg border border-gray-200 hover:border-blue-300 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-medium text-gray-900">{c.name}</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {c.total_combinations} combinations
                    {c.status === 'processing' &&
                      ` \u2022 ${c.completed_count}/${c.total_combinations} done`}
                  </p>
                </div>
                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[c.status] || ''}`}
                >
                  {c.status}
                </span>
              </div>

              {c.status === 'processing' && c.total_combinations > 0 && (
                <div className="mt-3 w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{
                      width: `${((c.completed_count + c.failed_count) / c.total_combinations) * 100}%`,
                    }}
                  />
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
