import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { apiClient } from '../lib/api';
import { Task, TaskPhase, TaskStatus } from '../types';
import { 
  LayoutDashboard, 
  Clock, 
  Play, 
  CheckCircle, 
  AlertCircle,
  MoreHorizontal,
  Plus
} from 'lucide-react';

const phaseColors: Record<TaskPhase, string> = {
  Submitted: 'text-dashboard-muted bg-dashboard-muted/20 border-dashboard-muted/30',
  Qualified: 'text-primary-400 bg-primary-500/20 border-primary-500/30',
  Running: 'text-primary-400 bg-primary-500/20 border-primary-500/30',
  Validating: 'text-blue-400 bg-blue-500/20 border-blue-500/30',
  AwaitingReview: 'text-amber-400 bg-amber-500/20 border-amber-500/30',
  Completed: 'text-emerald-400 bg-emerald-500/20 border-emerald-500/30',
  Failed: 'text-red-400 bg-red-500/20 border-red-500/30',
  Cancelled: 'text-dashboard-muted bg-dashboard-muted/20 border-dashboard-muted/30',
  Paused: 'text-amber-400 bg-amber-500/20 border-amber-500/30',
};

export default function Dashboard() {
  const [stats, setStats] = useState({
    totalTasks: 0,
    pending: 0,
    inProgress: 0,
    completed: 0,
    failed: 0,
    activeTasks: [] as Task[],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchDashboardData = async () => {
    try {
      const { tasks, total } = await apiClient.getTasks({ limit: 10 });
      
      const pending = tasks.filter(t => t.status === 'Pending').length;
      const inProgress = tasks.filter(t => t.status === 'InProgress').length;
      const completed = tasks.filter(t => t.status === 'Completed').length;
      const failed = tasks.filter(t => t.status === 'Failed').length;
      const activeTasks = tasks.slice(0, 5);

      setStats({
        totalTasks: total,
        pending,
        inProgress,
        completed,
        failed,
        activeTasks,
      });
      setLoading(false);
    } catch (error) {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="relative">
          <div className="h-16 w-16 border-4 border-primary-600/30 rounded-full animate-spin"></div>
          <div className="absolute top-0 left-0 h-16 w-16 border-4 border-primary-600 rounded-full border-t-transparent animate-spin"></div>
        </div>
      </div>
    );
  }

  const StatCard = ({ 
    title, 
    value, 
    icon: Icon, 
    color,
    trend 
  }: { 
    title: string; 
    value: number; 
    icon: any; 
    color: string;
    trend?: string;
  }) => (
    <Card className="hover:shadow-lg transition-shadow duration-300">
      <CardContent className="flex items-center justify-between p-6">
        <div>
          <p className="text-sm font-medium text-dashboard-muted mb-1">{title}</p>
          <div className="flex items-baseline gap-2">
            <h3 className="text-4xl font-bold text-dashboard-text">{value}</h3>
            {trend && (
              <span className="text-xs font-medium text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded-full">
                {trend}
              </span>
            )}
          </div>
        </div>
        <div className={`h-14 w-14 rounded-xl flex items-center justify-center ${color}`}>
          <Icon className="h-7 w-7" />
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="min-h-screen bg-dashboard-bg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 animate-fade-in-up">
          <div>
            <h1 className="text-3xl font-bold text-dashboard-text mb-2">Dashboard</h1>
            <p className="text-dashboard-muted">Overview of your DevFoundry environment</p>
          </div>
          <Button variant="primary" size="md" leftIcon={<Plus className="h-5 w-5" />}>
            New Task
          </Button>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 mb-8">
          <StatCard 
            title="Total Tasks" 
            value={stats.totalTasks} 
            icon={LayoutDashboard} 
            color="bg-primary-500/20 text-primary-400"
          />
          <StatCard 
            title="Pending" 
            value={stats.pending} 
            icon={Clock} 
            color="bg-amber-500/20 text-amber-400"
          />
          <StatCard 
            title="In Progress" 
            value={stats.inProgress} 
            icon={Play} 
            color="bg-blue-500/20 text-blue-400"
          />
          <StatCard 
            title="Completed" 
            value={stats.completed} 
            icon={CheckCircle} 
            color="bg-emerald-500/20 text-emerald-400"
          />
          <StatCard 
            title="Failed" 
            value={stats.failed} 
            icon={AlertCircle} 
            color="bg-red-500/20 text-red-400"
          />
        </div>

        {/* Recent Tasks */}
        <Card variant="elevated">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Recent Tasks</CardTitle>
              <Link to="/tasks">
                <Button variant="ghost" size="sm">
                  View All <MoreHorizontal className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                  <tr>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Task</th>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Phase</th>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                    <th className="text-left py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Created</th>
                    <th className="text-right py-4 px-6 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dashboard-border">
                  {stats.activeTasks.length > 0 ? (
                    stats.activeTasks.map((task) => (
                      <tr key={task.id} className="hover:bg-dashboard-card/30 transition-colors group">
                        <td className="py-4 px-6">
                          <Link 
                            to={`/tasks/${task.id}`} 
                            className="text-sm font-medium text-primary-400 hover:text-primary-300 hover:underline group-hover:text-primary-400"
                          >
                            {task.description.slice(0, 60)}
                          </Link>
                          <div className="text-xs text-dashboard-muted mt-1">
                            #{task.id.slice(0, 8)} • {new Date(task.createdAt).toLocaleDateString()}
                          </div>
                        </td>
                        <td className="py-4 px-6">
                          <Badge className={phaseColors[task.phase]}>{task.phase}</Badge>
                        </td>
                        <td className="py-4 px-6">
                          <Badge 
                            variant={
                              task.status === 'Completed' ? 'success' : 
                              task.status === 'Failed' ? 'danger' : 
                              task.status === 'Pending' ? 'warning' : 'primary'
                            }
                          >
                            {task.status}
                          </Badge>
                        </td>
                        <td className="py-4 px-6">
                          <span className="text-sm text-dashboard-muted">
                            {new Date(task.createdAt).toLocaleDateString()}
                          </span>
                        </td>
                        <td className="py-4 px-6 text-right">
                          <Link to={`/tasks/${task.id}`}>
                            <Button variant="ghost" size="sm">View</Button>
                          </Link>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="py-12 text-center">
                        <div className="flex flex-col items-center justify-center text-dashboard-muted">
                          <LayoutDashboard className="h-12 w-12 mb-3 opacity-50" />
                          <p className="text-sm">No recent tasks</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* System Status Bar */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full bg-emerald-500 animate-pulse"></div>
                <div>
                  <p className="text-sm font-medium text-dashboard-text">System Status</p>
                  <p className="text-xs text-dashboard-muted">All systems operational</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full bg-primary-500"></div>
                <div>
                  <p className="text-sm font-medium text-dashboard-text">API Status</p>
                  <p className="text-xs text-dashboard-muted">Response time: 45ms</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full bg-amber-500"></div>
                <div>
                  <p className="text-sm font-medium text-dashboard-text">Next Sync</p>
                  <p className="text-xs text-dashboard-muted">In 28 minutes</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
