import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge, TaskBadge, StatusBadge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Button } from '../components/ui/Button';
import { apiClient } from '../lib/api';
import { Task, TaskPhase, TaskStatus } from '../types';
import { 
  Search, 
  Filter, 
  Plus,
  X,
  Play,
  RotateCcw,
  Pause,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [phaseFilter, setPhaseFilter] = useState<TaskPhase | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [page, setPage] = useState(1);
  const [showNewTaskModal, setShowNewTaskModal] = useState(false);
  const [newTask, setNewTask] = useState({ description: '', projectId: '', userId: '' });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const itemsPerPage = 20;

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 15000);
    return () => clearInterval(interval);
  }, [page, phaseFilter, statusFilter]);

  const fetchTasks = async () => {
    try {
      const { tasks: taskList, total: totalCount } = await apiClient.getTasks({
        phase: phaseFilter === 'all' ? undefined : phaseFilter,
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: itemsPerPage,
        offset: (page - 1) * itemsPerPage,
      });
      setTasks(taskList);
      setTotal(totalCount ?? taskList.length);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (taskId: string) => {
    if (!window.confirm('Are you sure you want to cancel this task?')) return;

    try {
      await apiClient.updateTask(taskId, { status: 'Cancelled', phase: 'Cancelled' });
      fetchTasks();
    } catch (error) {
      console.error('Failed to cancel task:', error);
    }
  };

  const handleResume = async (taskId: string) => {
    try {
      await apiClient.updateTask(taskId, { status: 'Pending', phase: 'Qualified' });
      fetchTasks();
    } catch (error) {
      console.error('Failed to resume task:', error);
    }
  };

  const handleRetry = async (taskId: string) => {
    try {
      await apiClient.updateTask(taskId, {
        status: 'Pending',
        phase: 'Submitted'
      });
      fetchTasks();
    } catch (error) {
      console.error('Failed to retry task:', error);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError('');
    if (!newTask.description.trim() || !newTask.projectId.trim() || !newTask.userId.trim()) {
      setCreateError('All fields are required');
      return;
    }
    setCreating(true);
    try {
      await apiClient.createTask({
        description: newTask.description.trim(),
        projectId: newTask.projectId.trim(),
        userId: newTask.userId.trim(),
      });
      setShowNewTaskModal(false);
      setNewTask({ description: '', projectId: '', userId: '' });
      setPage(1);
      fetchTasks();
    } catch (error) {
      setCreateError('Failed to create task');
    } finally {
      setCreating(false);
    }
  };

  const filteredTasks = tasks.filter(task => {
    const matchesSearch = task.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesPhase = phaseFilter === 'all' || task.phase === phaseFilter;
    const matchesStatus = statusFilter === 'all' || task.status === statusFilter;
    return matchesSearch && matchesPhase && matchesStatus;
  });

  const totalPages = Math.max(1, Math.ceil(total / itemsPerPage));

  if (loading && tasks.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="relative">
          <div className="h-16 w-16 border-4 border-primary-600/30 rounded-full animate-spin"></div>
          <div className="absolute top-0 left-0 h-16 w-16 border-4 border-primary-600 rounded-full border-t-transparent animate-spin"></div>
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
            <h1 className="text-3xl font-bold text-dashboard-text mb-2">Tasks</h1>
            <p className="text-dashboard-muted">Manage and monitor all tasks</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              leftIcon={<Plus className="h-5 w-5" />}
              onClick={() => setShowNewTaskModal(true)}
            >
              New Task
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card className="mb-6" variant="elevated">
          <CardContent className="p-6">
            <div className="flex flex-col lg:flex-row gap-4">
                <div className="flex-1 relative">
                  <Input
                    placeholder="Search tasks..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    leftIcon={<Search className="h-4 w-4" />}
                    className="pl-10"
                  />
                  {searchTerm && (
                  <button
                    onClick={() => setSearchTerm('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-dashboard-muted hover:text-dashboard-text"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-3">
                <Select 
                  value={phaseFilter} 
                  onChange={(e) => {
                    setPhaseFilter(e.target.value as TaskPhase | 'all');
                    setPage(1);
                  }}
                  className="w-40"
                >
                  <option value="all">All Phases</option>
                  <option value="Submitted">Submitted</option>
                  <option value="Qualified">Qualified</option>
                  <option value="Running">Running</option>
                  <option value="Validating">Validating</option>
                  <option value="AwaitingReview">Awaiting Review</option>
                  <option value="Completed">Completed</option>
                  <option value="Failed">Failed</option>
                  <option value="Cancelled">Cancelled</option>
                  <option value="Paused">Paused</option>
                </Select>
                <Select 
                  value={statusFilter} 
                  onChange={(e) => {
                    setStatusFilter(e.target.value as TaskStatus | 'all');
                    setPage(1);
                  }}
                  className="w-40"
                >
                  <option value="all">All Statuses</option>
                  <option value="Pending">Pending</option>
                  <option value="InProgress">In Progress</option>
                  <option value="Completed">Completed</option>
                  <option value="Failed">Failed</option>
                  <option value="Cancelled">Cancelled</option>
                </Select>
                <Button 
                  variant="secondary" 
                  onClick={() => {
                    setSearchTerm('');
                    setPhaseFilter('all');
                    setStatusFilter('all');
                    setPage(1);
                  }}
                >
                  <X className="h-4 w-4 mr-2" />
                  Clear
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Task List */}
        <Card variant="elevated">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                <tr>
                  <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Task</th>
                  <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Phase</th>
                  <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                  <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">User</th>
                  <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Project</th>
                  <th className="text-right py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dashboard-border">
                {filteredTasks.length > 0 ? (
                  filteredTasks.map((task) => (
                    <tr key={task.id} className="hover:bg-dashboard-card/30 transition-colors group">
                      <td className="py-4 px-6">
                        <Link 
                          to={`/tasks/${task.id}`} 
                          className="text-sm font-medium text-primary-400 hover:text-primary-300 hover:underline"
                        >
                          {task.description}
                        </Link>
                        <div className="text-xs text-dashboard-muted mt-1">
                          #{task.id.slice(0, 8)} • {new Date(task.createdAt).toLocaleDateString()}
                        </div>
                      </td>
                      <td className="py-4 px-6">
                        <TaskBadge phase={task.phase} />
                      </td>
                      <td className="py-4 px-6">
                        <StatusBadge status={task.status} />
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm text-dashboard-text">{task.userId.slice(0, 8)}</span>
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm text-dashboard-muted">{task.projectId.slice(0, 8)}</span>
                      </td>
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Link to={`/tasks/${task.id}`}>
                            <Button variant="secondary" size="sm">View</Button>
                          </Link>
                          {(task.phase === 'Running' || task.phase === 'Validating' || task.phase === 'Paused') && (
                            <Button 
                              variant="danger" 
                              size="sm" 
                              onClick={() => handleCancel(task.id)}
                              leftIcon={<Pause className="h-4 w-4" />}
                            >
                              Cancel
                            </Button>
                          )}
                          {(task.phase === 'Cancelled' || task.phase === 'Failed') && (
                            <Button 
                              variant="primary" 
                              size="sm" 
                              onClick={() => handleRetry(task.id)}
                              leftIcon={<RotateCcw className="h-4 w-4" />}
                            >
                              Retry
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="py-12 text-center">
                      <div className="flex flex-col items-center justify-center text-dashboard-muted">
                        <Search className="h-12 w-12 mb-3 opacity-50" />
                        <p className="text-sm">No tasks found</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-6 py-4 border-t border-dashboard-border bg-dashboard-card/50">
              <span className="text-sm text-dashboard-muted">
                Page {page} of {totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page === 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  leftIcon={<ChevronLeft className="h-4 w-4" />}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page === totalPages}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  rightIcon={<ChevronRight className="h-4 w-4" />}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* New Task Modal */}
      {showNewTaskModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" onClick={() => !creating && setShowNewTaskModal(false)}>
          <div
            className="w-full max-w-lg bg-dashboard-card border border-dashboard-border rounded-xl shadow-2xl animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-dashboard-border">
              <h2 className="text-lg font-semibold text-dashboard-text">Create New Task</h2>
              <button
                onClick={() => !creating && setShowNewTaskModal(false)}
                className="text-dashboard-muted hover:text-dashboard-text p-1 rounded-lg hover:bg-dashboard-muted/20"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleCreateTask} className="p-6 space-y-4">
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-dashboard-text-secondary">Description</label>
                <textarea
                  className="block w-full rounded-lg border border-dashboard-border bg-dashboard-bg px-3 py-2 text-sm text-dashboard-text shadow-sm placeholder:text-dashboard-muted focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                  rows={3}
                  placeholder="Describe the task..."
                  value={newTask.description}
                  onChange={(e) => setNewTask(prev => ({ ...prev, description: e.target.value }))}
                  required
                />
              </div>
              <Input
                label="Project ID"
                placeholder="e.g. dev-foundry"
                value={newTask.projectId}
                onChange={(e) => setNewTask(prev => ({ ...prev, projectId: e.target.value }))}
                required
              />
              <Input
                label="User ID"
                placeholder="e.g. admin"
                value={newTask.userId}
                onChange={(e) => setNewTask(prev => ({ ...prev, userId: e.target.value }))}
                required
              />
              {createError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-sm text-red-400">{createError}</p>
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setShowNewTaskModal(false)}
                  disabled={creating}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary" disabled={creating}>
                  {creating ? (
                    <div className="flex items-center gap-2">
                      <div className="h-4 w-4 border-2 border-white/30 rounded-full animate-spin" />
                      <span>Creating...</span>
                    </div>
                  ) : (
                    'Create Task'
                  )}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
