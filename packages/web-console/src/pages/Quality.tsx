import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { apiClient } from '../lib/api';
import {
  Gauge,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  Server,
  Boxes,
} from 'lucide-react';

interface Outcomes {
  total_tasks: number;
  completed_count: number;
  failed_count: number;
  cancelled_count: number;
  pending_count: number;
  avg_retries: number;
  avg_duration_s: number;
}

const phaseBarColors: Record<string, string> = {
  Submitted: 'bg-dashboard-muted',
  Qualified: 'bg-primary-500',
  Running: 'bg-primary-600',
  Validating: 'bg-purple-500',
  AwaitingReview: 'bg-amber-500',
  Completed: 'bg-emerald-500',
  Failed: 'bg-red-500',
  Cancelled: 'bg-dashboard-muted',
  Paused: 'bg-amber-400',
};

const formatDuration = (seconds: number) => {
  if (!seconds) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m}m ${s}s` : `${m}m`;
};

export default function Quality() {
  const [days, setDays] = useState(30);
  const [outcomes, setOutcomes] = useState<Outcomes | null>(null);
  const [phases, setPhases] = useState<Array<{ phase: string; count: number }>>([]);
  const [admission, setAdmission] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [outcomesRes, phasesRes, admissionRes] = await Promise.all([
        apiClient.getAnalyticsOutcomes({ days }),
        apiClient.getAnalyticsPhases(),
        apiClient.getAdmission(),
      ]);
      setOutcomes(outcomesRes);
      setPhases(phasesRes.phases || []);
      setAdmission(admissionRes);
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    setLoading(true);
    void reload();
    const interval = setInterval(() => void reload(), 15000);
    return () => clearInterval(interval);
  }, [reload]);

  const successRate = outcomes && outcomes.total_tasks > 0
    ? Math.round((outcomes.completed_count / outcomes.total_tasks) * 100)
    : null;
  const maxPhaseCount = Math.max(1, ...phases.map((p) => p.count));

  const StatCard = ({
    title,
    value,
    icon: Icon,
    color,
  }: {
    title: string;
    value: number;
    icon: any;
    color: string;
  }) => (
    <Card className="hover:shadow-lg transition-shadow duration-300">
      <CardContent className="flex items-center justify-between p-6">
        <div>
          <p className="text-sm font-medium text-dashboard-muted mb-1">{title}</p>
          <h3 className="text-4xl font-bold text-dashboard-text">{value}</h3>
        </div>
        <div className={`h-14 w-14 rounded-xl flex items-center justify-center ${color}`}>
          <Icon className="h-7 w-7" />
        </div>
      </CardContent>
    </Card>
  );

  if (loading && !outcomes) {
    return (
      <div className="min-h-screen bg-dashboard-bg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <p className="text-dashboard-muted">Loading quality &amp; admission…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dashboard-bg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 animate-fade-in-up">
          <div>
            <h1 className="text-3xl font-bold text-dashboard-text mb-2">Quality &amp; Admission</h1>
            <p className="text-dashboard-muted">Task outcomes, phase distribution, and cluster admission</p>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={String(days)}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-32"
            >
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </Select>
            <Button
              variant="secondary"
              size="md"
              leftIcon={<RefreshCw className="h-4 w-4" />}
              onClick={() => void reload()}
            >
              Refresh
            </Button>
          </div>
        </div>

        {/* Load Error */}
        {loadError && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
            Gateway error: {loadError}
          </div>
        )}

        {/* Outcome Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-4">
          <StatCard
            title="Accepted"
            value={outcomes?.completed_count ?? 0}
            icon={CheckCircle}
            color="bg-emerald-500/20 text-emerald-400"
          />
          <StatCard
            title="Failed"
            value={outcomes?.failed_count ?? 0}
            icon={XCircle}
            color="bg-red-500/20 text-red-400"
          />
          <StatCard
            title="Awaiting Review"
            value={outcomes?.pending_count ?? 0}
            icon={Clock}
            color="bg-amber-500/20 text-amber-400"
          />
        </div>

        {/* Secondary Stats */}
        <Card variant="elevated" className="mb-6">
          <CardContent className="p-6">
            {outcomes && outcomes.total_tasks > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-dashboard-text-secondary">Total Tasks</p>
                  <p className="text-2xl font-bold text-dashboard-text mt-1">{outcomes.total_tasks}</p>
                </div>
                <div>
                  <p className="text-sm text-dashboard-text-secondary">Success Rate</p>
                  <p className="text-2xl font-bold text-dashboard-text mt-1">{successRate}%</p>
                </div>
                <div>
                  <p className="text-sm text-dashboard-text-secondary">Avg Retries</p>
                  <p className="text-2xl font-bold text-dashboard-text mt-1">{outcomes.avg_retries ?? 0}</p>
                </div>
                <div>
                  <p className="text-sm text-dashboard-text-secondary">Avg Duration</p>
                  <p className="text-2xl font-bold text-dashboard-text mt-1">{formatDuration(outcomes.avg_duration_s)}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-dashboard-muted text-center py-2">
                No tasks in this period — outcomes will appear once tasks run.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Phase Distribution */}
        <Card variant="elevated" className="mb-6">
          <CardContent className="p-6">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                <Boxes className="h-5 w-5 text-purple-400" />
                Phase Distribution
              </h3>
              {phases.length > 0 ? (
                <div className="space-y-3">
                  {phases.map((p) => (
                    <div key={p.phase} className="flex items-center gap-4">
                      <span className="text-sm text-dashboard-text-secondary w-36 shrink-0">
                        {p.phase.replace(/([A-Z])/g, ' $1').trim()}
                      </span>
                      <div className="flex-1 h-6 bg-dashboard-bg rounded-md overflow-hidden border border-dashboard-border">
                        <div
                          className={`h-full rounded-md ${phaseBarColors[p.phase] || 'bg-primary-500'}`}
                          style={{ width: `${Math.max(2, (p.count / maxPhaseCount) * 100)}%` }}
                        />
                      </div>
                      <Badge variant="secondary" className="w-12 text-center">{p.count}</Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-dashboard-muted text-center py-2">
                  No phase data yet — submit a task to populate the distribution.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Capacity Admission */}
        <Card variant="elevated">
          <CardContent className="p-6">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                <Server className="h-5 w-5 text-primary-400" />
                Capacity Admission
              </h3>
              {admission ? (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-dashboard-text-secondary">CPU Limit</p>
                      <p className="text-2xl font-bold text-dashboard-text mt-1">{admission.limits?.cpu ?? '—'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-dashboard-text-secondary">RAM Limit (GB)</p>
                      <p className="text-2xl font-bold text-dashboard-text mt-1">{admission.limits?.ram ?? '—'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-dashboard-text-secondary">Disk Limit (GB)</p>
                      <p className="text-2xl font-bold text-dashboard-text mt-1">{admission.limits?.disk ?? '—'}</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 bg-dashboard-card/50 rounded-lg border border-dashboard-border/50">
                      <p className="text-sm text-dashboard-text-secondary">Queue Depth</p>
                      <p className="text-2xl font-bold text-dashboard-text mt-1">{admission.queue?.depth ?? 0}</p>
                    </div>
                    <div className="p-4 bg-dashboard-card/50 rounded-lg border border-dashboard-border/50">
                      <p className="text-sm text-dashboard-text-secondary">Awaiting Review</p>
                      <p className="text-2xl font-bold text-dashboard-text mt-1">{admission.queue?.awaitingReview ?? 0}</p>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-dashboard-text-secondary flex items-center gap-2">
                          <Gauge className="h-4 w-4" /> CPU Usage
                        </span>
                        <span className="text-sm text-dashboard-text">{admission.resources?.cpu?.usage ?? 0}%</span>
                      </div>
                      <div className="h-2 bg-dashboard-bg rounded-full overflow-hidden border border-dashboard-border">
                        <div
                          className="h-full bg-primary-500 rounded-full"
                          style={{ width: `${Math.min(100, admission.resources?.cpu?.usage ?? 0)}%` }}
                        />
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-dashboard-text-secondary flex items-center gap-2">
                          <Gauge className="h-4 w-4" /> Memory Usage
                        </span>
                        <span className="text-sm text-dashboard-text">{admission.resources?.memory?.usage ?? 0}%</span>
                      </div>
                      <div className="h-2 bg-dashboard-bg rounded-full overflow-hidden border border-dashboard-border">
                        <div
                          className="h-full bg-purple-500 rounded-full"
                          style={{ width: `${Math.min(100, admission.resources?.memory?.usage ?? 0)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-sm text-dashboard-muted text-center py-2">
                  Admission data unavailable.
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
