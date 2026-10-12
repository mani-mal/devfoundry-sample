import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { apiClient } from '../lib/api';
import { EvidenceItem, TaskCheckpoint, TaskPhase, TaskOutcome, TaskStatus } from '../types';

const phaseColors: Record<TaskPhase, string> = {
  Submitted: 'bg-dashboard-muted/20 text-dashboard-muted border border-dashboard-muted/30',
  Qualified: 'bg-primary-500/20 text-primary-300 border border-primary-500/30',
  Running: 'bg-primary-500/20 text-primary-300 border border-primary-500/30',
  Validating: 'bg-purple-500/20 text-purple-300 border border-purple-500/30',
  AwaitingReview: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
  Completed: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
  Failed: 'bg-red-500/20 text-red-300 border border-red-500/30',
  Cancelled: 'bg-dashboard-muted/20 text-dashboard-muted border border-dashboard-muted/30',
  Paused: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
};

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  
  const [task, setTask] = useState<any>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [reviewReason, setReviewReason] = useState('');
  const [showReviewPacket, setShowReviewPacket] = useState(false);
  const [reviewPacket, setReviewPacket] = useState<any>(null);
  const [packetLoaded, setPacketLoaded] = useState(false);
  const [packetLoading, setPacketLoading] = useState(false);
  const [attempts, setAttempts] = useState<Array<{ attempt_id: string; success: boolean; reason?: string; created_at: string }>>([]);
  const [workspaceStatus, setWorkspaceStatus] = useState<string | null>(null);
  const [workspaceChecking, setWorkspaceChecking] = useState(false);

  useEffect(() => {
    if (taskId) {
      fetchTask();
      fetchEvidence();
      fetchAttempts();
    }
  }, [taskId]);

  const fetchTask = async () => {
    try {
      const data = await apiClient.getTask(taskId!);
      setTask(data);
      setLoading(false);
    } catch (err) {
      setError('Failed to load task');
      setLoading(false);
    }
  };

  const fetchEvidence = async () => {
    try {
      const data = await apiClient.getTaskEvidence(taskId!);
      setEvidence(data.evidence || []);
    } catch (error) {
      console.error('Failed to fetch evidence:', error);
    }
  };

  const fetchAttempts = async () => {
    try {
      const data = await apiClient.getAttempts(taskId!);
      setAttempts(data.attempts || []);
    } catch (error) {
      console.error('Failed to fetch attempts:', error);
    }
  };

  const runAction = async (fn: () => Promise<unknown>) => {
    setActionError('');
    setActionLoading(true);
    try {
      await fn();
      await fetchTask();
      await fetchAttempts();
    } catch (err) {
      setActionError((err as any).response?.data?.error || (err as Error).message || 'Action failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = () => {
    if (!window.confirm('Are you sure you want to cancel this task?')) return;
    void runAction(() => apiClient.cancelTask(taskId!));
  };

  const handleApprove = (disposition: 'approve' | 'reject') => {
    void runAction(() => apiClient.approveTask(taskId!, disposition, reviewReason || undefined));
    setReviewReason('');
  };

  const handleRetry = () => void runAction(() => apiClient.retryTask(taskId!));
  const handlePause = () => void runAction(() => apiClient.pauseTask(taskId!));
  const handleResume = () => void runAction(() => apiClient.resumeTask(taskId!));

  const handleLoadPacket = async () => {
    setPacketLoading(true);
    try {
      const data = await apiClient.getReviewPacket(taskId!);
      setReviewPacket(data?.packet ?? null);
      setPacketLoaded(true);
    } catch (err) {
      console.error('Failed to load review packet:', err);
    } finally {
      setPacketLoading(false);
    }
  };

  const handleCheckWorkspace = async () => {
    if (!task.workspaceId) return;
    setWorkspaceChecking(true);
    try {
      const data = await apiClient.getWorkspace(task.workspaceId);
      setWorkspaceStatus(data.workspace?.status || 'unknown');
    } catch (err) {
      const msg = (err as any).response?.status === 404
        ? 'Workspace not found'
        : ((err as any).response?.data?.error || 'OpenCode unavailable');
      setWorkspaceStatus(msg);
    } finally {
      setWorkspaceChecking(false);
    }
  };

  const formatPhase = (phase: TaskPhase) => {
    return phase.charAt(0).toUpperCase() + phase.slice(1);
  };

  const formatStatus = (status: TaskStatus) => {
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-dashboard-bg flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-primary-600 border-t-transparent"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-dashboard-bg flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error}</p>
          <Button onClick={() => navigate('/tasks')}>Back to Tasks</Button>
        </div>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="min-h-screen bg-dashboard-bg flex items-center justify-center">
        <div className="text-center">
          <p className="text-dashboard-text-secondary mb-4">Task not found</p>
          <Button onClick={() => navigate('/tasks')}>Back to Tasks</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dashboard-bg">
      <header className="bg-dashboard-card border-b border-dashboard-border px-6 py-4">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-dashboard-text">Task Details</h1>
            <p className="text-sm text-dashboard-text-secondary">ID: {task.id}</p>
          </div>
          <Button variant="secondary" onClick={() => navigate('/tasks')}>Back to Tasks</Button>
        </div>
      </header>

      {actionError && (
        <div className="mx-6 mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p className="text-sm text-red-400">{actionError}</p>
        </div>
      )}

      <main className="p-6 space-y-6">
        {/* Task Header */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2">
            <h2 className="text-lg font-semibold text-dashboard-text mb-4">Task Information</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-dashboard-text-secondary">Description</p>
                <p className="text-dashboard-text font-medium mt-1">{task.description}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Phase</p>
                <div className="mt-1">
                  <Badge className={phaseColors[task.phase]}>{formatPhase(task.phase)}</Badge>
                </div>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Status</p>
                <div className="mt-1">
                  <Badge variant={task.status === 'Completed' ? 'success' : task.status === 'Failed' ? 'danger' : 'default'}>
                    {formatStatus(task.status)}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">User</p>
                <p className="text-dashboard-text font-medium mt-1">{task.userId}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Project</p>
                <p className="text-dashboard-text font-medium mt-1">{task.projectId}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Repository</p>
                <p className="text-dashboard-text font-medium mt-1">{task.baseCommit}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Target Branch</p>
                <p className="text-dashboard-text font-medium mt-1">{task.targetBranch}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Model Route</p>
                <p className="text-dashboard-text font-medium mt-1">{task.modelRoute}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Capacity Profile</p>
                <p className="text-dashboard-text font-medium mt-1">{task.capacityProfile}</p>
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-dashboard-text mb-4">Execution Info</h2>
            <div className="space-y-3">
              <div>
                <p className="text-sm text-dashboard-text-secondary">Worker ID</p>
                <p className="text-dashboard-text font-medium mt-1">{task.workspaceId}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Retry Count</p>
                <p className="text-dashboard-text font-medium mt-1">{task.retryCount}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Created</p>
                <p className="text-dashboard-text font-medium mt-1">
                  {new Date(task.createdAt).toLocaleString()}
                </p>
              </div>
              {task.startedAt && (
                <div>
                  <p className="text-sm text-dashboard-text-secondary">Started</p>
                  <p className="text-dashboard-text font-medium mt-1">
                    {new Date(task.startedAt).toLocaleString()}
                  </p>
                </div>
              )}
              {task.completedAt && (
                <div>
                  <p className="text-sm text-dashboard-text-secondary">Completed</p>
                  <p className="text-dashboard-text font-medium mt-1">
                    {new Date(task.completedAt).toLocaleString()}
                  </p>
                </div>
              )}
            </div>

            <div className="mt-6 pt-6 border-t border-dashboard-border space-y-2">
              {!['Completed', 'Failed', 'Cancelled'].includes(task.status) && (
                <Button variant="danger" className="w-full" disabled={actionLoading} onClick={handleCancel}>Cancel Task</Button>
              )}
              {task.phase === 'AwaitingReview' && (
                <>
                  <Input
                    placeholder="Review reason (optional)"
                    value={reviewReason}
                    onChange={(e) => setReviewReason(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button variant="primary" className="flex-1" disabled={actionLoading} onClick={() => handleApprove('approve')}>Approve</Button>
                    <Button variant="danger" className="flex-1" disabled={actionLoading} onClick={() => handleApprove('reject')}>Reject</Button>
                  </div>
                </>
              )}
              {task.status === 'Failed' && (
                <Button variant="primary" className="w-full" disabled={actionLoading} onClick={handleRetry}>Retry Task</Button>
              )}
              {task.phase === 'Running' && (
                <Button variant="secondary" className="w-full" disabled={actionLoading} onClick={handlePause}>Pause</Button>
              )}
              {task.status === 'Paused' && (
                <Button variant="secondary" className="w-full" disabled={actionLoading} onClick={handleResume}>Resume</Button>
              )}
            </div>
          </Card>
        </div>

        {/* Skills and Context */}
        <Card title="Skills & Context">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="font-medium text-dashboard-text mb-2">Installed Skills</h3>
              <div className="flex flex-wrap gap-2">
                {task.skills.length > 0 ? (
                  task.skills.map((skill: string, idx: number) => (
                    <Badge key={idx} variant="secondary">{skill}</Badge>
                  ))
                ) : (
                  <p className="text-dashboard-text-secondary">No skills installed</p>
                )}
              </div>
            </div>
            <div>
              <h3 className="font-medium text-dashboard-text mb-2">Tool Permissions</h3>
              <div className="flex flex-wrap gap-2">
                {task.toolPermissions.length > 0 ? (
                  task.toolPermissions.map((perm: any, idx: number) => (
                    <Badge key={idx} variant="info">{perm.toolId}</Badge>
                  ))
                ) : (
                  <p className="text-dashboard-text-secondary">No tool permissions</p>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Evidence & Artifacts */}
        <Card title="Evidence & Artifacts">
          <div className="space-y-4">
            {evidence.length > 0 ? (
              evidence.map((item: EvidenceItem, idx: number) => (
                <div key={idx} className="bg-dashboard-bg rounded-md p-4 border border-dashboard-border">
                  <div className="flex items-center justify-between mb-2">
                    <Badge variant={item.type === 'security' ? 'danger' : item.type === 'test' ? 'info' : 'default'}>
                      {item.type}
                    </Badge>
                    <span className="text-xs text-dashboard-text-secondary">
                      {new Date(item.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-sm text-dashboard-text">
                    <pre className="whitespace-pre-wrap bg-dashboard-card p-3 rounded-md overflow-x-auto">
                      {item.content}
                    </pre>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-dashboard-text-secondary">No evidence available</p>
            )}
          </div>
        </Card>

        {/* Checkpoint (if available) */}
        {task.checkpoint && (
          <Card title="Checkpoint">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-dashboard-text-secondary">Snapshot ID</p>
                <p className="text-dashboard-text font-medium mt-1">{task.checkpoint.snapshotId}</p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Workspace State</p>
                <p className="text-dashboard-text font-medium mt-1">
                  {task.checkpoint.workspaceState.worktreePath}
                </p>
              </div>
              <div>
                <p className="text-sm text-dashboard-text-secondary">Session ID</p>
                <p className="text-dashboard-text font-medium mt-1">
                  {task.checkpoint.sessionState.sessionId}
                </p>
              </div>
            </div>
          </Card>
        )}

        {/* Review Packet */}
        <Card title="Review Packet">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-dashboard-text-secondary">
                Consolidated review evidence generated when the task enters review.
              </p>
              <Button
                variant="secondary"
                size="sm"
                disabled={packetLoading}
                onClick={() => {
                  setShowReviewPacket(!showReviewPacket);
                  if (!packetLoaded && !showReviewPacket) void handleLoadPacket();
                }}
              >
                {showReviewPacket ? 'Hide' : 'Load Review Packet'}
              </Button>
            </div>
            {showReviewPacket && (
              packetLoaded ? (
                reviewPacket ? (
                  <pre className="text-xs text-dashboard-text bg-dashboard-bg rounded-md p-4 border border-dashboard-border overflow-auto max-h-96">
                    {JSON.stringify(reviewPacket, null, 2)}
                  </pre>
                ) : (
                  <p className="text-sm text-dashboard-muted">No review packet generated yet</p>
                )
              ) : (
                <p className="text-sm text-dashboard-muted">Loading…</p>
              )
            )}
          </div>
        </Card>

        {/* Attempt History */}
        <Card title="Attempt History">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Attempt</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Result</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Reason</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dashboard-border">
                {attempts.length > 0 ? (
                  attempts.map((attempt) => (
                    <tr key={attempt.attempt_id} className="hover:bg-dashboard-card/30 transition-colors">
                      <td className="py-3 px-4">
                        <span className="text-sm font-medium text-dashboard-text">#{attempt.attempt_id.slice(0, 8)}</span>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant={attempt.success ? 'success' : 'danger'}>
                          {attempt.success ? '✓ Success' : '✗ Failed'}
                        </Badge>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-sm text-dashboard-text-secondary">{attempt.reason || '—'}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-sm text-dashboard-muted">
                          {new Date(attempt.created_at).toLocaleString()}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-sm text-dashboard-muted">
                      No attempts recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Workspace */}
        <Card title="Workspace">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <p className="text-sm text-dashboard-text-secondary">Workspace ID</p>
              <p className="text-dashboard-text font-medium mt-1">{task.workspaceId || '—'}</p>
              {workspaceStatus && (
                <p className="text-sm text-primary-300 mt-2">
                  Status: {workspaceStatus}
                </p>
              )}
            </div>
            <Button
              variant="secondary"
              size="sm"
              disabled={!task.workspaceId || workspaceChecking}
              onClick={handleCheckWorkspace}
            >
              Check Workspace
            </Button>
          </div>
        </Card>
      </main>
    </div>
  );
}
