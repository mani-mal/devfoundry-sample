import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
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

  useEffect(() => {
    if (taskId) {
      fetchTask();
      fetchEvidence();
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

  const handleCancel = async () => {
    if (!window.confirm('Are you sure you want to cancel this task?')) return;

    try {
      await apiClient.updateTask(taskId!, { status: 'Cancelled', phase: 'Cancelled' });
      navigate('/tasks');
    } catch (error) {
      console.error('Failed to cancel task:', error);
    }
  };

  const handleResume = async () => {
    try {
      await apiClient.updateTask(taskId!, { status: 'Pending', phase: 'Qualified' });
      fetchTask();
    } catch (error) {
      console.error('Failed to resume task:', error);
    }
  };

  const handleRetry = async () => {
    try {
      await apiClient.updateTask(taskId!, { 
        status: 'Pending', 
        phase: 'Submitted'
      });
      fetchTask();
    } catch (error) {
      console.error('Failed to retry task:', error);
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
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

            {task.phase === 'Running' || task.phase === 'Validating' || task.phase === 'Paused' ? (
              <div className="mt-6 pt-6 border-t border-dashboard-border">
                <Button variant="danger" className="w-full" onClick={handleCancel}>Cancel Task</Button>
              </div>
            ) : task.phase === 'Cancelled' || task.phase === 'Failed' ? (
              <div className="mt-6 pt-6 border-t border-dashboard-border">
                <Button variant="primary" className="w-full" onClick={handleRetry}>Retry Task</Button>
              </div>
            ) : null}

            {task.phase === 'Paused' && (
              <div className="mt-4">
                <Button variant="secondary" className="w-full" onClick={handleResume}>Resume</Button>
              </div>
            )}
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
      </main>
    </div>
  );
}
